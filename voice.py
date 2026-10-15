"""Offline command parsing and bounded web-search retrieval; no speech leaves the Pi."""
import html
import re
import time
from difflib import SequenceMatcher
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


def normalize(text):
    return re.sub(r'[^\w\s]', ' ', text.lower()).strip()

class WakeGate:
    def __init__(self): self.until = 0
    def feed(self, text, now=None):
        now = time.monotonic() if now is None else now
        text = ' '.join(normalize(text).split())
        match = re.match(r'^hey frame\b\s*(.*)', text)
        if match:
            command = match.group(1)
            self.until = now + 8 if not command else 0
            return command if command else '__listening__'
        if now < self.until and text:
            self.until = 0
            return text
        return None

def parse_command(text, movies):
    text = ' '.join(normalize(text).split())
    actions = {'pause':'pause_only', 'pause movie':'pause_only', 'resume':'resume', 'resume movie':'resume',
               'stop':'stop', 'stop movie':'stop', 'mute':'mute_on', 'unmute':'mute_off',
               'volume up':'volume_up', 'turn it up':'volume_up', 'volume down':'volume_down',
               'turn it down':'volume_down', 'show library':'home', 'go home':'home',
               'test audio':'audio_test', 'test sound':'audio_test'}
    if text in actions: return {'action':actions[text]}
    match = re.fullmatch(r'(?:set )?volume(?: to)? (.+?)(?: percent)?',text)
    if match:
        value=match.group(1)
        numbers={'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,
                 'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,
                 'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90,'hundred':100}
        if value=='one hundred':value='100'
        if value.isdigit():return {'action':'volume','value':max(0,min(100,int(value)))}
        words=value.split()
        if len(words)<=2 and all(w in numbers for w in words):return {'action':'volume','value':min(100,sum(numbers[w] for w in words))}
    if text.startswith(('search the web for ', 'search web for ', 'search for ', 'look up ')):
        query = re.sub(r'^(?:search (?:the web |web )?for |look up )','',text).strip()
        if not query: raise ValueError('Say what you want to search for')
        return {'action':'web_search','query':query[:200]}
    if text.startswith(('play ', 'watch ')):
        title = re.sub(r'^(play|watch) (the movie )?','',text).strip()
        if not title: raise ValueError('Say a movie title after play')
        exact = [m for m in movies if normalize(m['title']) == title]
        if len(exact)==1: return {'action':'play','id':exact[0]['id']}
        ranked = sorted(((SequenceMatcher(None,title,normalize(m['title'])).ratio(),m) for m in movies), key=lambda x:x[0],reverse=True)
        if not ranked or ranked[0][0]<.78: raise ValueError('No matching movie found. Try its full title.')
        if len(exact)>1 or (len(ranked)>1 and ranked[0][0]-ranked[1][0]<.12):
            raise ValueError('More than one movie matches. Choose it from the library.')
        return {'action':'play','id':ranked[0][1]['id']}
    raise ValueError('Try: play a movie title, pause, resume, volume up, or search the web for a topic.')

class SearchParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.results=[];self.current=None;self.capture=None;self.depth=0
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs);cls=attrs.get('class','').split()
        if tag=='a' and 'result__a' in cls:
            link=html.unescape(attrs.get('href',''))
            if link.startswith('//'):link='https:'+link
            parsed=urlsplit(link)
            if parsed.hostname and parsed.hostname.endswith('duckduckgo.com'):
                link=parse_qs(parsed.query).get('uddg',[link])[0]
            if urlsplit(link).scheme not in {'http','https'}:return
            self.current={'title':'','url':link,'snippet':''};self.results.append(self.current);self.capture='title';self.depth=1
        elif 'result__snippet' in cls and self.current:
            self.capture='snippet';self.depth=1
        elif self.capture:self.depth+=1
    def handle_endtag(self, tag):
        if self.capture:
            self.depth-=1
            if self.depth<=0:self.capture=None
    def handle_data(self,data):
        if self.capture and self.current:self.current[self.capture]+=data

def parse_search_feed(raw):
    root=ET.fromstring(raw)
    results=[]
    for item in root.findall('./channel/item'):
        url=item.findtext('link','')
        if urlsplit(url).scheme not in {'http','https'}:continue
        clean=lambda text:' '.join(html.unescape(re.sub(r'<[^>]*>','',text)).split())
        results.append({'title':clean(item.findtext('title','')), 'url':url, 'snippet':clean(item.findtext('description',''))})
    return results[:5]

def search_web(query):
    # A public RSS response avoids rendering a browser. Fall back if the feed is unavailable.
    try:
        url='https://www.bing.com/search?'+urlencode({'format':'rss','q':query})
        with urlopen(Request(url,headers={'User-Agent':'Frame/2.2 local movie center'}),timeout=5) as response:
            results=parse_search_feed(response.read(1024*1024))
        if results:return results
    except (OSError,ValueError,ET.ParseError):pass
    url='https://html.duckduckgo.com/html/?'+urlencode({'q':query})
    request=Request(url,headers={'User-Agent':'Frame/2.2 local movie center'})
    with urlopen(request,timeout=5) as response:
        raw=response.read(1024*1024).decode('utf-8',errors='replace')
    parser=SearchParser();parser.feed(raw)
    results=[{k:' '.join(v.split()) if k!='url' else v for k,v in item.items()} for item in parser.results[:5]]
    if not results:raise ValueError('Search is unavailable or returned no results. Try again later.')
    return results
