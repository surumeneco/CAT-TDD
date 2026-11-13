"""W09 regression: literal Markdown syntax cannot become a source dependency."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cat-system'/'scripts'))
from cat_promote import promote,Blocked
from test_cat_compile_readable import fm


def fixture(body):
    td=tempfile.TemporaryDirectory()
    root=Path(td.name)
    source=root/'Lifecycle'/'CAT'/'Draft'/'Demo.md'
    source.parent.mkdir(parents=True)
    target=root/'docs'/'requirements.md'
    target.parent.mkdir(parents=True)
    target.write_text('source',encoding='utf-8')
    source.write_text(fm('tce','demo.process.tce',[],language='en')+'\n'+body,
                      encoding='utf-8')
    output=root/'Docs'/'Processes'/'Demo.md'
    return td,source,output


class PromotionMarkdownLiteralTests(unittest.TestCase):
    def test_inline_code_link_is_literal_not_a_missing_dependency(self):
        tick=chr(96)
        td,source,output=fixture(
            tick+'[example](../../../docs/does-not-exist.md)'+tick+'\n'
            '[real](../../../docs/requirements.md)\n')
        with td:
            self.assertEqual(promote(source,output,'decision:synthetic')['status'],'passed')
            result=output.read_text(encoding='utf-8')
            self.assertIn(tick+'[example](../../../docs/does-not-exist.md)'+tick,result)
            self.assertIn('[real](../../docs/requirements.md)',result)

    def test_multibacktick_code_span_literal_and_reference_definition(self):
        ticks=chr(96)*2
        td,source,output=fixture(
            ticks+' [literal](../../../docs/no.md) '+chr(96)+
            '[in code](../../../docs/no.md)'+chr(96)+' '+ticks+'\n'
            '[document][id]\n'
            '[id]: ../../../docs/requirements.md "source"\n')
        with td:
            self.assertEqual(promote(source,output,'decision:synthetic')['status'],'passed')
            result=output.read_text(encoding='utf-8')
            self.assertIn(ticks+' [literal](../../../docs/no.md) '+chr(96)+
                          '[in code](../../../docs/no.md)'+chr(96)+' '+ticks,result)
            self.assertIn('[id]: ../../docs/requirements.md "source"',result)

    def test_escaped_link_and_escaped_reference_definition_are_literal(self):
        slash=chr(92)
        td,source,output=fixture(
            slash+'[literal](../../../docs/not-a-link.md)\n'+
            slash+'![literal](../../../docs/not-an-image.md)\n'+
            slash+'[ref]: ../../../docs/not-a-reference.md\n'+
            '[real](../../../docs/requirements.md)\n')
        with td:
            self.assertEqual(promote(source,output,'decision:synthetic')['status'],'passed')
            result=output.read_text(encoding='utf-8')
            self.assertIn(slash+'[literal](../../../docs/not-a-link.md)',result)
            self.assertIn(slash+'![literal](../../../docs/not-an-image.md)',result)
            self.assertIn(slash+'[ref]: ../../../docs/not-a-reference.md',result)
            self.assertIn('[real](../../docs/requirements.md)',result)

    def test_indented_code_example_is_not_a_markdown_link(self):
        td,source,output=fixture(
            '    [example](../../../docs/never-exists.md)\n'
            '\t[example][missing]\n'
            '[real](../../../docs/requirements.md)\n')
        with td:
            self.assertEqual(promote(source,output,'decision:synthetic')['status'],'passed')
            self.assertIn('    [example](../../../docs/never-exists.md)',
                          output.read_text(encoding='utf-8'))

    def test_actual_missing_link_remains_a_non_destructive_failure(self):
        td,source,output=fixture('[missing](../../../docs/not-found.md)\n')
        with td:
            original=source.read_bytes()
            with self.assertRaisesRegex(Blocked,'does not resolve'):
                promote(source,output,'decision:synthetic')
            self.assertEqual(source.read_bytes(),original)
            self.assertFalse(output.exists())


if __name__=='__main__': unittest.main()
