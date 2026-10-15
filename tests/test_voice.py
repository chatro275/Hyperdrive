import unittest
from voice import WakeGate, parse_command, SearchParser, parse_search_feed

class VoiceTests(unittest.TestCase):
    def test_wake_phrase_required_and_followup_expires(self):
        gate=WakeGate()
        self.assertIsNone(gate.feed('play dune',100))
        self.assertIsNone(gate.feed('they said hey frame play dune',100))
        self.assertEqual(gate.feed('hey frame play dune',101),'play dune')
        self.assertIsNone(gate.feed('pause',102))
        self.assertEqual(gate.feed('hey frame',110),'__listening__')
        self.assertEqual(gate.feed('pause',112),'pause')
        gate.feed('hey frame',120)
        self.assertIsNone(gate.feed('stop',129))
    def test_movie_matching_and_ambiguity(self):
        movies=[{'id':1,'title':'Interstellar'}, {'id':2,'title':'Dune'}]
        self.assertEqual(parse_command('play interstellar',movies),{'action':'play','id':1})
        with self.assertRaises(ValueError):parse_command('play a totally absent title',movies)
        with self.assertRaises(ValueError):parse_command('play dune',movies+[{'id':3,'title':'Dune'}])
    def test_controls_are_explicit_and_power_not_voice_enabled(self):
        self.assertEqual(parse_command('pause',[])['action'],'pause_only')
        self.assertEqual(parse_command('resume',[])['action'],'resume')
        self.assertEqual(parse_command('mute',[])['action'],'mute_on')
        self.assertEqual(parse_command('volume 999',[])['value'],100)
        self.assertEqual(parse_command('set volume to fifty percent',[])['value'],50)
        for phrase in ('reboot','shutdown','install update','run shell command'):
            with self.assertRaises(ValueError):parse_command(phrase,[])
    def test_search_only_explicit_query(self):
        self.assertEqual(parse_command('search the web for raspberry pi',[]),{'action':'web_search','query':'raspberry pi'})
        with self.assertRaises(ValueError):parse_command('what is the news',[])
    def test_search_html_only_http_links_and_plain_text(self):
        parser=SearchParser()
        parser.feed('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">A <b>result</b></a><a class="result__snippet">Some text</a><a class="result__a" href="javascript:alert(1)">Bad</a>')
        self.assertEqual(len(parser.results),1)
        self.assertEqual(parser.results[0],{'title':'A result','url':'https://example.com','snippet':'Some text'})
    def test_search_feed_extracts_results_without_executing_markup(self):
        results=parse_search_feed(b'<rss><channel><item><title>Test</title><link>https://example.com</link><description>&lt;b&gt;Snippet&lt;/b&gt;</description></item><item><link>javascript:bad</link></item></channel></rss>')
        self.assertEqual(results,[{'title':'Test','url':'https://example.com','snippet':'Snippet'}])
