"""
Тесты для ErrorInterpreter.
"""

import unittest
from brain.error_interpreter import ErrorInterpreter, Solution, InterpretedError


class ClassifyErrorTests(unittest.TestCase):
    """Тесты классификации ошибок."""
    
    def setUp(self):
        self.interpreter = ErrorInterpreter()
    
    def test_403_classified_as_rate_limit(self):
        result = self.interpreter._classify_error("403 forbidden")
        self.assertEqual(result, "rate_limit")
    
    def test_429_classified_as_rate_limit(self):
        result = self.interpreter._classify_error("429 too many requests")
        self.assertEqual(result, "rate_limit")
    
    def test_401_classified_as_auth(self):
        result = self.interpreter._classify_error("401 unauthorized")
        self.assertEqual(result, "auth")
    
    def test_credentials_issue_classified_as_auth(self):
        result = self.interpreter._classify_error("check your credentials")
        self.assertEqual(result, "auth")
    
    def test_timeout_classified_as_network_timeout(self):
        result = self.interpreter._classify_error("request timed out")
        self.assertEqual(result, "network_timeout")
    
    def test_connection_refused_classified_as_network_refused(self):
        result = self.interpreter._classify_error("connection refused")
        self.assertEqual(result, "network_refused")
    
    def test_500_classified_as_server_error(self):
        result = self.interpreter._classify_error("500 internal server error")
        self.assertEqual(result, "server_error")
    
    def test_unknown_error_classified_as_unknown(self):
        result = self.interpreter._classify_error("something weird happened")
        self.assertEqual(result, "unknown")


class InterpretWithContextTests(unittest.TestCase):
    """Тесты интерпретации с контекстом задачи."""
    
    def setUp(self):
        self.interpreter = ErrorInterpreter()
    
    def test_rate_limit_with_many_channels(self):
        result = self.interpreter.interpret(
            error="403 Forbidden",
            context={
                'task': 'собирать посты из телеграм каналов',
                'params': {'channels': '@a, @b, @c, @d, @e, @f, @g, @h, @i, @j, @k, @l'}
            }
        )
        
        self.assertEqual(result.error_type, "rate_limit")
        self.assertIn("12", result.likely_cause)  # упоминает количество
        self.assertTrue(len(result.solutions) > 0)
        self.assertIn("Варианты решения", result.user_message)
    
    def test_rate_limit_suggests_reduce_items(self):
        result = self.interpreter.interpret(
            error="403 Forbidden",
            context={
                'task': 'собирать посты',
                'params': {'channels': ['@a', '@b', '@c', '@d', '@e', '@f', '@g', '@h']}
            }
        )
        
        # Должен предложить уменьшить количество
        solution_titles = [s.title for s in result.solutions]
        self.assertTrue(
            any('меньш' in t.lower() or 'начать' in t.lower() for t in solution_titles)
        )
    
    def test_rsshub_rate_limit_suggests_local_instance(self):
        result = self.interpreter.interpret(
            error="403 Forbidden",
            context={
                'task': 'rsshub telegram',
                'params': {'channels': '@a, @b, @c'}
            }
        )
        
        # Должен предложить локальный RSSHub
        solution_descriptions = [s.description for s in result.solutions]
        self.assertTrue(
            any('docker' in d.lower() or 'локальн' in d.lower() for d in solution_descriptions)
        )
    
    def test_auth_error_asks_for_credentials(self):
        result = self.interpreter.interpret(
            error="401 Unauthorized",
            context={'task': 'получить данные', 'params': {}}
        )
        
        self.assertEqual(result.error_type, "auth")
        self.assertTrue(
            any('ключ' in s.description.lower() or 'токен' in s.description.lower() 
                for s in result.solutions)
        )


class UserMessageFormatTests(unittest.TestCase):
    """Тесты формата сообщения пользователю."""
    
    def setUp(self):
        self.interpreter = ErrorInterpreter()
    
    def test_message_has_header(self):
        result = self.interpreter.interpret("403 Forbidden", {})
        self.assertIn("лимит", result.user_message.lower())
    
    def test_message_has_cause(self):
        result = self.interpreter.interpret(
            "403 Forbidden",
            {'params': {'channels': '@a, @b, @c, @d, @e, @f, @g, @h, @i, @j'}}
        )
        self.assertIn("Причина", result.user_message)
    
    def test_message_has_numbered_solutions(self):
        result = self.interpreter.interpret("403 Forbidden", {})
        self.assertIn("1.", result.user_message)
    
    def test_message_ends_with_question(self):
        result = self.interpreter.interpret("403 Forbidden", {})
        self.assertTrue(
            "?" in result.user_message or 
            "выбери" in result.user_message.lower()
        )
    
    def test_no_raw_error_code_in_message(self):
        """Сообщение не должно содержать сырой код ошибки."""
        result = self.interpreter.interpret("403 Forbidden", {})
        # user_message должен быть человекочитаемым, без "403"
        # (403 может быть в original_error, но не в user_message)
        self.assertNotIn("403", result.user_message)


class CanRetryTests(unittest.TestCase):
    """Тесты определения возможности retry."""
    
    def setUp(self):
        self.interpreter = ErrorInterpreter()
    
    def test_rate_limit_with_many_items_can_retry(self):
        result = self.interpreter.interpret(
            "403 Forbidden",
            {'params': {'channels': ['@a', '@b', '@c', '@d', '@e', '@f', '@g']}}
        )
        
        self.assertTrue(result.can_retry_with_modification)
        self.assertIsNotNone(result.suggested_modification)
        self.assertIn('reduce_items_to', result.suggested_modification)
    
    def test_rate_limit_with_few_items_cannot_auto_retry(self):
        result = self.interpreter.interpret(
            "403 Forbidden",
            {'params': {'channels': ['@a', '@b']}}
        )
        
        # С малым количеством нечего уменьшать
        self.assertFalse(result.can_retry_with_modification)
    
    def test_timeout_can_retry_after_delay(self):
        result = self.interpreter.interpret("timeout", {})
        
        self.assertTrue(result.can_retry_with_modification)
        self.assertIn('retry_after_seconds', result.suggested_modification)


class IntegrationTests(unittest.TestCase):
    """Интеграционные тесты полного flow."""
    
    def setUp(self):
        self.interpreter = ErrorInterpreter()
    
    def test_full_flow_30_telegram_channels(self):
        """Тест реального сценария с 30 телеграм-каналами."""
        channels = ", ".join([f"@channel{i}" for i in range(30)])
        
        result = self.interpreter.interpret(
            error="Forbidden - perhaps check your credentials?",
            context={
                'task': 'каждый день в 11 утра собирать новости из телеграм каналов',
                'step': 'n8n_create_from_template',
                'params': {
                    'channels': channels,
                    'template': 'social_parser'
                },
                'service': 'rsshub'
            }
        )
        
        # Проверяем что всё корректно интерпретировано
        self.assertEqual(result.error_type, "rate_limit")
        self.assertIn("30", result.likely_cause)
        self.assertTrue(len(result.solutions) >= 2)
        self.assertIn("Варианты", result.user_message)
        self.assertTrue(result.can_retry_with_modification)
        
        # Сообщение должно быть понятным человеку
        self.assertNotIn("credentials?", result.user_message)
        self.assertNotIn("Forbidden", result.user_message)


if __name__ == '__main__':
    unittest.main()
