"""Regression tests for SQL migration statement splitting."""
import unittest

from layer1.onchain_postgres import _split_sql_statements


class PostgresMigrationStatementSplitterTests(unittest.TestCase):
    def test_semicolons_inside_line_comments_do_not_create_statements(self):
        source = (
            "-- migration note; this semicolon is not SQL\n"
            "CREATE TABLE first_table (id INTEGER);\n"
            "-- another note; still not SQL\n"
            "CREATE TABLE second_table (id INTEGER);\n"
        )
        self.assertEqual(
            _split_sql_statements(source),
            (
                "CREATE TABLE first_table (id INTEGER)",
                "CREATE TABLE second_table (id INTEGER)",
            ),
        )

    def test_semicolons_inside_block_comments_do_not_create_statements(self):
        source = (
            "/* migration note; still comment */\n"
            "CREATE TABLE first_table (id INTEGER);\n"
            "/* second; note */ CREATE TABLE second_table (id INTEGER);"
        )
        self.assertEqual(
            _split_sql_statements(source),
            (
                "CREATE TABLE first_table (id INTEGER)",
                "CREATE TABLE second_table (id INTEGER)",
            ),
        )

    def test_semicolons_inside_quoted_values_and_identifiers_are_preserved(self):
        source = (
            'CREATE TABLE "semi;colon" (value TEXT);\n'
            "INSERT INTO \"semi;colon\" VALUES ('value;still value');"
        )
        self.assertEqual(
            _split_sql_statements(source),
            (
                'CREATE TABLE "semi;colon" (value TEXT)',
                "INSERT INTO \"semi;colon\" VALUES ('value;still value')",
            ),
        )

    def test_doubled_quote_escapes_do_not_end_quoted_regions(self):
        source = "INSERT INTO sample VALUES ('it''s; valid'); SELECT \"a\"\";b\" FROM sample;"
        self.assertEqual(
            _split_sql_statements(source),
            (
                "INSERT INTO sample VALUES ('it''s; valid')",
                'SELECT "a"";b" FROM sample',
            ),
        )

    def test_unterminated_comment_or_quote_fails_closed(self):
        for source in ("SELECT 1; /* unterminated", "SELECT 'unterminated;"):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    _split_sql_statements(source)


if __name__ == "__main__":
    unittest.main()
