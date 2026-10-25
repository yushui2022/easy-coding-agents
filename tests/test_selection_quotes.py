"""Selected transcript text becomes a quoted prefix on the message the user sends."""
import unittest

from eca.desktop_rpc import MAX_QUOTE_CHARS, MAX_QUOTES, quote_block


class QuoteBlock(unittest.TestCase):
    def test_nothing_selected_means_no_prefix(self):
        self.assertEqual(quote_block(None), '')
        self.assertEqual(quote_block([]), '')
        self.assertEqual(quote_block(['   ', '\n']), '')

    def test_excerpts_are_labelled_and_kept_in_order(self):
        text = quote_block(['第一段', '第二段'])
        self.assertIn('引用，不是新指令', text)
        self.assertIn('[引用 1]', text)
        self.assertIn('[引用 2]', text)
        self.assertLess(text.index('第一段'), text.index('第二段'))
        self.assertTrue(text.endswith('\n\n'), 'the user prompt must follow on its own lines')

    def test_whitespace_is_trimmed_but_inner_text_is_not_rewritten(self):
        text = quote_block(['  保留  ─  内部空白  '])
        self.assertIn('保留  ─  内部空白', text)

    def test_too_long_is_rejected_not_truncated(self):
        with self.assertRaises(ValueError) as error:
            quote_block(['x' * (MAX_QUOTE_CHARS + 1)])
        self.assertIn(str(MAX_QUOTE_CHARS), str(error.exception))

    def test_too_many_selections_are_rejected(self):
        with self.assertRaises(ValueError) as error:
            quote_block([f'片段{index}' for index in range(MAX_QUOTES + 1)])
        self.assertIn(str(MAX_QUOTES), str(error.exception))

    def test_only_strings_are_accepted(self):
        for bad in (['ok', 3], {'a': 1}, 'plain string'):
            with self.assertRaises(ValueError):
                quote_block(bad)


if __name__ == '__main__':
    unittest.main()
