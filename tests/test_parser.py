import unittest

from mash.parser import parse


class ParserTests(unittest.TestCase):
    def test_blank_and_comment(self):
        for line in ("", "  \t", "# ignored"):
            self.assertIsNone(parse(line))

    def test_quotes_escapes_and_empty_arguments(self):
        result = parse(r'''echo "hello world" '|' '' a\ b pre"fix" \>''')
        self.assertEqual(result.commands[0].argv, ["echo", "hello world", "|", "", "a b", "prefix", ">"])

    def test_quoted_operators_are_words(self):
        self.assertEqual(parse('echo ">" "&" "2>"').commands[0].argv, ["echo", ">", "&", "2>"])

    def test_pipeline_and_background_without_spaces(self):
        result = parse("cat<in|grep error|wc -l>out&")
        self.assertTrue(result.background)
        self.assertEqual([c.argv for c in result.commands], [["cat"], ["grep", "error"], ["wc", "-l"]])
        self.assertEqual(result.commands[0].redirects, [("<", "in")])
        self.assertEqual(result.commands[-1].redirects, [(">", "out")])

    def test_redirections_preserve_order(self):
        result = parse('echo x > first >> "second file" 2>errors 2>>more')
        self.assertEqual(result.commands[0].redirects,
                         [(">", "first"), (">>", "second file"), ("2>", "errors"), ("2>>", "more")])

    def test_number_inside_word_is_not_a_descriptor(self):
        self.assertEqual(parse('echo x2>file').commands[0].argv, ["echo", "x2"])
        self.assertEqual(parse('echo "2">file').commands[0].argv, ["echo", "2"])

    def test_comments_only_start_at_word_boundary(self):
        self.assertEqual(parse('echo x#y "#" # comment').commands[0].argv, ["echo", "x#y", "#"])

    def test_double_quote_backslash_rules(self):
        self.assertEqual(parse(r'echo "a\qb\"c\\d"').commands[0].argv, ['echo', 'a\\qb"c\\d'])

    def test_invalid_input(self):
        for line in ('| cat', 'cat |', 'cat || wc', 'a && b', 'a ; b', 'a << b',
                     'echo >', 'echo > | wc', 'echo > ""', '&', 'echo & wc',
                     'echo "unterminated', 'echo \\', '> file', '""', '"" | cat',
                     'echo \x00', "echo '\x00'", 'echo \\\x00'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse(line)


if __name__ == '__main__':
    unittest.main()
