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
        self.assertEqual(parse_command('install update',[])['action'],'updates')
        for phrase in ('reboot','shutdown','run shell command'):
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

    def test_hyper_wake_and_legacy_alias(self):
        gate=WakeGate()
        self.assertEqual(gate.feed('hey hyper storage space',100),'storage space')
        self.assertEqual(gate.feed('hey high per pause',101),'pause')
        self.assertIsNone(gate.feed('they said hey hyper stop',102))
        self.assertEqual(gate.feed('hey hyper',103),'__listening__')
        self.assertEqual(gate.feed('list files',104),'list files')
        self.assertIsNone(gate.feed('stop',105))

    def test_expanded_playback_and_storage_commands(self):
        for phrase,action in [('storage space','storage_space'),('list files','list_files'),('list folders','list_folders'),('subtitles on','subtitles_on'),('start over','restart_movie'),('open hyperdrive','hyperdrive')]:
            self.assertEqual(parse_command(phrase,[])['action'],action)
        self.assertEqual(parse_command('create folder called Holidays',[])['name'],'Holidays')
        self.assertEqual(parse_command('list files in Holidays',[])['name'],'Holidays')
        self.assertEqual(parse_command('skip forward thirty seconds',[]),{'action':'seek_seconds','value':30})
        with self.assertRaises(ValueError):parse_command('skip forward 99999 seconds',[])
        self.assertTrue(parse_command('add dune to watchlist',[{'id':2,'title':'Dune'}])['favorite'])

    def test_enhancer_quiet_speech_clipping_and_silence(self):
        from voice import AudioEnhancer
        from array import array
        import math
        quiet=array('h',(int(300*math.sin(2*math.pi*500*n/16000)) for n in range(4000))).tobytes()
        enhancer=AudioEnhancer(16000)
        for _ in range(10):output=array('h',enhancer.process(quiet))
        self.assertGreater(max(output),600)
        self.assertLessEqual(max(output),28000)
        self.assertLessEqual(enhancer.metrics['gain'],4)
        original=AudioEnhancer(16000,'off');self.assertEqual(original.process(quiet),quiet)
        silence=bytes(8000);self.assertEqual(AudioEnhancer(16000).process(silence),silence)
        loud=array('h',[32767]*4000).tobytes();processed=array('h',enhancer.process(loud))
        self.assertEqual(enhancer.metrics['clipped'],100)
        self.assertTrue(all(-32768<=x<=32767 for x in processed))

class Hyper28Tests(unittest.TestCase):
    def test_natural_commands(self):
        for text,action in [('could you take me home please','hyperdrive'),('please end the movie','end_movie'),('check for software updates','check_updates'),('update hyperdrive','updates'),('can you pause the movie','pause_only'),('fix movie audio','audio_setup')]:
            self.assertEqual(parse_command(text,[])['action'],action)
    def test_dual_mic_arbitration(self):
        from voice_worker import MicArbiter
        gate=MicArbiter()
        self.assertTrue(gate.claim(0,0));self.assertFalse(gate.claim(1,1))
        gate.finished(2)
        self.assertFalse(gate.claim(1,4));self.assertTrue(gate.claim(1,6))
    def test_microphones_have_separate_capture_and_close_on_start_error(self):
        from voice_worker import Microphone
        from unittest.mock import Mock
        sd=Mock();sd.query_devices.return_value={'default_samplerate':16000,'name':'USB mic'}
        first=Mock();second=Mock();sd.RawInputStream.side_effect=[first,second]
        factory=Mock()
        a=Microphone(sd,factory,None,1,'balanced');b=Microphone(sd,factory,None,2,'balanced')
        self.assertIsNot(a.queue,b.queue);self.assertIsNot(a.gate,b.gate)
        a.close();b.close();first.close.assert_called_once();second.close.assert_called_once()
        bad=Mock();bad.start.side_effect=RuntimeError('disconnected');sd.RawInputStream.side_effect=None;sd.RawInputStream.return_value=bad
        with self.assertRaises(RuntimeError):Microphone(sd,factory,None,3,'balanced')
        bad.close.assert_called_once()
