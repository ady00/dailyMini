#!/root/dailyMini/venv/bin/python3

from email.quoprimime import unquote
import browser_cookie3
import requests
import requests.utils
import os
import decompress
import re
import json
import puz
import sys
import html
import datetime as date
import time
import base64
import version
from supabase import create_client, Client
from datetime import datetime, timezone
import uuid





if sys.version_info >= (3, 11): from datetime import UTC
else: import datetime as datetime_fix; UTC=datetime_fix.timezone.utc
import json

os.environ['myUsername'] = 'username'
os.environ['myPassword'] = 'secret'



CACHE_DATA = False
LOG_CALLS = None

# These unicode characters are just used to draw the crossword grid to stdout
BLOCK_LEFT = "\u2590"
BLOCK_MID = "\u2588"
BLOCK_RIGHT = "\u258c"
TITLE_LINE = "\u2501"

# Different possibilities for each cell in the NYT's JSON data structure
NYT_TYPE_BLOCK = 0     # Black cell, no clues or answer
NYT_TYPE_NORMAL = 1    # Normal cell, could be a rebus
NYT_TYPE_CIRCLED = 2   # Cell with a circle around it as for letters part of a theme
NYT_TYPE_GRAY = 3      # A cell filled in as gray
NYT_TYPE_INVISIBLE = 4 # An "invisible" cell, generally something outside the main grid

LATIN1_SUBS = {
    # For converting clues etc. into Latin-1 (ISO-8859-1) format;
    # value None means let the encoder insert a Latin-1 equivalent
    u"\n": u" ",
    u"\r": u" ",
    u'“': u'"',
    u'”': u'"',
    u'‘': u"'",
    u'’': u"'",
    u'–': u'-',
    u'—': u'--',
    u'…': u'...',
    u'№': u'No.',
    u'π': u'pi',
    u'€': u'EUR',
    u'•': u'*',
    u'†': u'[dagger]',
    u'‡': u'[double dagger]',
    u'™': u'[TM]',
    u'‹': u'<',
    u'›': u'>',
    u'←': u'<--',
    u'■': None,
    u'☐': None,
    u'→': u'-->',
    u'♣': "Clubs",
    u'√': None,
    u'♠': "Spades",
    u'✓': None,
    u'♭': None,
    u'♂': None,
    u'★': u'*',
    u'θ': u'theta',
    u'β': u'beta',
    u'Č': None,
    u'𝚫': u'Delta',
    u'❤︎': None,
    u'✔': None,
    u'⚓': None,
    u'♦': "Diamonds",
    u'♥': "Hearts",
    u'☹': None,
    u'☮': None,
    u'☘': None,
    u'◯': None,
    u'▢': None,
    u'∑': None,
    u'∃': None,
    u'↓': None,
    u'⁎': u'*',
    u'η': u'eta',
    u'α': u'alpha',
    u'Ω': u'Omega',
    u'ō': None,
}
# Some rules to remove HTML like things with text versions for the .puz files
HTML_TO_TEXT_RULES = [
    ("<i>(.*?)</i>", "_\\1_"),              # "<i>Italic</i>" -> "_Italic_"
    ("<em>(.*?)</em>", "_\\1_"),            # "<em>Italic</em>" -> "_Italic_"
    ("<sub>(.*?)</sub>", "\\1"),            # "KNO<sub>3</sub>" -> "KNO3"
    ("<sup>([0-9 ]+)</sup>", "^\\1"),       # "E=MC<sup>2</sup>" -> "E=MC^2"
    ("<sup>(.*?)</sup>", "\\1"),            # "103<sup>rd</sup>" -> "103rd" (Note, after the numeric 'sup')
    ("<br( /|)>", " / "),                   # "A<br>B<br>C" -> "A / B / C"
    ("<s>(.*?)</s>", "[*cross out* \\1]"),  # "<s>Crossed Out</s>" -> "[*cross out* Crossed out]"
    ("<[^>]+>", ""),                        # Remove other things that look like HTML, but leave bare "<" alone.
    ("&nbsp;", " "),                        # Replace HTML's non-breaking spaces into normal spaces
]


def get_browsers():
    return {
        "Chrome": browser_cookie3.chrome,
        "Chromium": browser_cookie3.chromium,

        "Opera": browser_cookie3.opera,
        "Microsoft Edge": browser_cookie3.edge,
        "Firefox": browser_cookie3.firefox,
    }


def get_user_filename(filename):
    if os.name == "nt":
        homedir = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        homedir = format(os.path.expanduser("~"))
    return os.path.join(homedir, filename)


def pick_browser():
    # Ask the user for which browser they want to use
    options = get_browsers()
    settings_file = get_user_filename('nytxw_puz.json')
    settings = {}
    if os.path.isfile(settings_file):
        with open(settings_file) as f:
            settings = json.load(f)

    if os.path.isfile(get_cookie_cache_filename()):
        options["Cached Cookies"] = None

    default = settings.get('default')
    while True:
        default_number = None
        keys = list(sorted(options))
        for i, desc in enumerate(keys):
            if default is not None and desc == default:
                default_number = str(i + 1)
        
        selection = input(f"Please select a browser that's logged into NYTimes.com{' [' + default_number + ']' if default_number else ''}: ")
        try:
            if len(selection) == 0 and default_number:
                selection = default_number
            selection = int(selection)
            if selection >= 1 and selection <= len(options):
                selection = keys[selection - 1]
                break
        except:
            pass
    
    settings['default'] = selection
    if default != selection:
        with open(settings_file, 'wt') as f:
            json.dump(settings, f)

    return selection


# Internal helper to load a URL, optionally log the data, to make
# debugging remotely a tiny bit easier
def get_url(cookies, url):
    cookies = requests.utils.cookiejar_from_dict(cookies)
    
    resp = requests.get(url, cookies=cookies).content
   
    resp = resp.decode("utf-8")
    return resp


def get_cookie_cache_filename():
    return get_user_filename("nytxw_puz.cookies.json")


def load_cookies(browser):
    # Pull out the nytimes cookies from the user's browser
    # Cache the information to avoid a roundtrip to the browser if possible
    if browser == "Cached Cookies":
        with open(get_cookie_cache_filename(), "rt") as f:
            cookies = json.load(f)
    else:
        cookies = get_browsers()[browser](domain_name='nytimes.com')
        cookies = requests.utils.dict_from_cookiejar(cookies)
        with open(get_cookie_cache_filename(), "wt") as f:
            json.dump(cookies, f)

    return cookies


def get_puzzle_from_id(cookies, puzzle_id):
    # Get the puzzle itself
    puzzle_url = f"https://www.nytimes.com/svc/crosswords/v6/puzzle/{puzzle_id}.json"
    new_format = get_url(cookies, puzzle_url)
    new_format = json.loads(new_format)

    # The response is formatted somewhat differently than it used to be, so create a format
    # that looks like it used to
    resp = new_format["body"][0]
    resp["meta"] = {}
    # TODO: Notes might be stored elsewhere, need to verify
    for cur in ["publicationDate", "title", "editor", "copyright", "constructors", "notes"]:
        if cur in new_format:
            resp["meta"][cur] = new_format[cur]
    resp["dimensions"]["columnCount"] = resp["dimensions"]["width"]
    resp["dimensions"]["rowCount"] = resp["dimensions"]["height"]

    resp["gamePageData"] = resp

    return resp


def get_puzzle(url, browser):
    cache = {}
    if CACHE_DATA:
        # Simple cache, useful for debugging, grows to stupid
        # size over time, so it's off generally
        if os.path.isfile(".cached.json"):
            with open(".cached.json", "r", encoding="utf-8") as f:
                cache = json.load(f)

    if url not in cache:

        cookies = load_cookies(browser)
        for _ in range(4):
            # Load the webpage, its inline javascript includes the puzzle data
            resp = get_url(cookies, url)

            # NY Times is moving to a new system for puzzles, handle both, since 
            # it doesn't seem to have migrated 100% of the accounts out there

            # Option #1, see if this is the old style encoded javascript blob:
            # Look for the javascript, it's easist here to just use a regex
            m = re.search("(pluribus|window.gameData) *= *['\"](?P<data>.*?)['\"]", resp)
            if m is not None:
                # Pull out the data element
                resp = m.group("data")
                if "%" in resp:
                    # Which is url-encoded
                    resp = decompress.decode(resp)
                    # And LZString compressed
                    resp = decompress.decompress(resp)
                else:
                    # New format, this is now base64 encoded
                    resp = base64.b64decode(resp).decode("utf-8")
                    # And _then_ url-encoded
                    resp = decompress.decode(resp)
                # And a JSON blob
                resp = json.loads(resp)
                # All done, we can stop retries
                break

            # Option #2, try the new version with a gaming REST endpoint:
            # Try to find the puzzle description:
            m = re.search("window\\.gameData *= *(?P<json>{.*?})", resp)
            if m is not None:
                # Pull out the puzzle key
                key = m.group("json")
                key = json.loads(key)
                key = key['filename']

                # Request the puzzle meta-data
                api = f"https://www.nytimes.com/svc/crosswords/v6/puzzle/{key}.json"
                metadata = get_url(cookies, api)
                metadata = json.loads(metadata)

                resp = get_puzzle_from_id(cookies, metadata['id'])

                # All done
                break

            # Something didn't look right, try again
            time.sleep(1)

        cache[url] = resp
        if CACHE_DATA:
            with open(".cached.json", "w", newline="", encoding="utf-8") as f:
                json.dump(cache, f)
    
    return cache[url]


def print_puzzle(p):
    # Dump out the puzzle, just a helper mostly to debug things
    p = p['gamePageData']
    width, height = p["dimensions"]["columnCount"], p["dimensions"]["rowCount"]
    for y in range(height):
        row = " "
        extra = ""
        shown = ""
        for x in range(width):
            cell = y * width + x
            cell = p["cells"][cell]
            if 'moreAnswers' in cell:
                # This is an oddball answer, note all the possibilities
                row += "- "
                temp = []
                if 'answer' in cell:
                    temp += [cell['answer']]
                temp += cell['moreAnswers']['valid']
                temp = f" ({', '.join(temp)})"
                if temp != shown:
                    shown = temp
                    extra += temp
            elif 'answer' in cell:
                # Normal answer, but if it's a rebus answer, show the first character
                # and the rebus answer to the side
                if len(cell['answer']) > 1:
                    extra += " " + cell['answer']
                    row += cell['answer'][0].lower() + " "
                else:
                    row += cell['answer'] + " "
            else:
                # Non-clue cell, just mark it
                row += "# "

        # Turn the "#" into block characters
        for x in range(len(row), 0, -1):
            row = row.replace(" " + "# " * x, BLOCK_LEFT + BLOCK_MID.join([BLOCK_MID] * x) + BLOCK_RIGHT)

        # And output the results


def latin1ify(s):
    source_string = s

    # Make a Unicode string compliant with the Latin-1 (ISO-8859-1) character
    # set; the Across Lite v1.3 format only supports Latin-1 encoding

    # Use table to convert the most common Unicode glyphs
    for search, replace in LATIN1_SUBS.items():
        if replace is not None:
            s = s.replace(search, replace)

    # Convert anything remaining using replacements like '\N{WINKING FACE}'
    s = s.encode('ISO-8859-1', 'namereplace').decode('ISO-8859-1')

    # Replace HTML like things into plain text
    for pattern, repl in HTML_TO_TEXT_RULES:
        s = re.sub(pattern, repl, s)

    s = s.strip()
    

    return s


def gridchar(c):
    if 'answer' in c:
        # The usual case
             
        return latin1ify(c['answer'][0])
    if 'moreAnswers' in c:
        more = c.get('moreAnswers', [])
        if isinstance(more, dict):
            more = more['valid']

        for a in more:
            if len(a) == 1:
                return latin1ify(a)
        return 'X'

    # Black square
    return '.'


def gridrebus(c):
    if 'answer' in c:
        if len(c['answer']) > 1:
            # This cell has a rebus answer, but first, see if we can find a 
            # answer that's already easy to use
            more = c.get('moreAnswers', [])
            if isinstance(more, dict):
                more = more['valid']
            answers = [c['answer']] + more
            for possible in answers:
                if possible == latin1ify(possible) and len(possible) > 1:
                    # This is a possibility that works well
                    return possible
            # Nothing useful, just use the first clue
            return answers[0]
    return None


def data_to_puz(puzzle):
    p = puz.Puzzle()
    data = puzzle['gamePageData']

    # Basic header
    p.title = 'New York Times Crossword'
    if 'publicationDate' in data['meta']:
        year, month, day = data['meta']['publicationDate'].split('-')
        d = date.date(int(year), int(month), int(day))
        months = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December']
        dow = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
               'Saturday', 'Sunday']
        p.title = ('NY Times, ' + dow[d.weekday()] + ', ' + months[d.month] +
                   ' ' + str(d.day) + ', ' + str(d.year))
        if 'title' in data['meta']:
            p.title += ' ' + latin1ify(data['meta']['title'].upper())
    elif 'title' in data['meta']:
        p.title = latin1ify(data['meta']['title'].upper())
    p.author = ', '.join(latin1ify(c) for c in data['meta']['constructors'])
    if 'editor' in data['meta']:
        p.author += ' / ' + latin1ify(data['meta']['editor'])
    if 'copyright' in data['meta']:
        p.copyright = '© ' + data['meta']['copyright'] + ', The New York Times'

    # Pull out the size of the puzzle
    p.height = data["dimensions"]["rowCount"]
    p.width = data["dimensions"]["columnCount"]

    

    

    


    # Fill out the main grid
    p.solution = ''.join(gridchar(x) for x in data['cells'])


    gridnums = []

    for cell in data['cells']:
        label = cell.get('label', '0')
        gridnums.append(label)

    substrings = [p.solution[i:i+5] for i in range(0, len(p.solution), p.width)]

    array_2d = [list(substring) + ['.'] * ((p.width) - len(substring)) for substring in substrings]

    

    across_answers = [''.join(row).replace('.', '') for row in array_2d]

    down_answers = [''.join(col).replace('.', '') for col in zip(*array_2d)]

    across_clue_real = []
    down_clue_real = []


    

    p.fill = ''.join('-' if 'answer' in x else '.' for x in data['cells'])

    # And the clues, they're HTML text here, so decode them, Across Lite expects them in
    # crossword order, not the NYT clue order, order them correctly
    seen = set()
    clues = []
    for cell in data['cells']:
        for clue in cell.get('clues', []):
            if clue not in seen:
                seen.add(clue)
                temp = data['clues'][clue]['text']
                
                if data['clues'][clue]['direction'] == "Across":

                    temp = data['clues'][clue]['text']

                    if isinstance(temp, list):
                        temp = temp[0]
                    if isinstance(temp, dict):
                        temp = temp.get("plain", "")

                    fin = data['clues'][clue]['label']
                    fin += ". "
                    fin += temp

                    across_clue_real.append(fin)

                if data['clues'][clue]['direction'] == "Down":

                    temp = data['clues'][clue]['text']

                    if isinstance(temp, list):
                        temp = temp[0]
                    if isinstance(temp, dict):
                        temp = temp.get("plain", "")

                    fin = data['clues'][clue]['label']
                    fin += ". "
                    fin += temp





                    down_clue_real.append(fin)
                
                if isinstance(temp, list):
                    temp = temp[0]
                if isinstance(temp, dict):
                    temp = temp.get("plain", "")
                clues.append(latin1ify(html.unescape(temp)))
    p.clues = clues


    # See if any of the answers is multi-character (rebus)
    if max([len(x['answer']) for x in data['cells'] if 'answer' in x]) > 1:
        # We have at least one rebus answer, so setup the rebus data fields
        rebus = p.create_empty_rebus()

        # And find all the rebus answers and add them to the data
        for cell in data['cells']:
            rebus.add_rebus(gridrebus(cell))

    # See if any grid squares are marked up with circles
    if any(x['type'] in (NYT_TYPE_CIRCLED, NYT_TYPE_GRAY) for x in data['cells'] if 'type' in x):
        markup = p.markup()
        markup.markup = [0] * (p.width * p.height)

        for i, cell in enumerate(data['cells']):
            if 'type' in cell and cell['type'] in (NYT_TYPE_CIRCLED, NYT_TYPE_GRAY):
                markup.markup[cell.get('index', i)] = puz.GridMarkup.Circled

    # Check for any notes in puzzle (e.g., Sep 11, 2008)
    if data['meta'].get('notes', None) is not None:
        p.notes = '\n\n'.join(latin1ify(x['text']) for x in data['meta']['notes']
                              if 'text' in x)


    
    gridnums = [int(value) for value in gridnums]

    

    # Print the across and down clues
    



    if 'publicationDate' in data['meta']:
        year, month, day = data['meta']['publicationDate'].split('-')
    
    date_full = day + "/" + month + "/" + year

    filename_full = day + "-" + month + "-" + year

    


    crossword_data = {
        "title": p.title,
        "author": p.author,
        "editor": "Will Shortz",
        "copyright": p.copyright,
        "publisher": "The New York Times",
        "date": date_full,
        "notepad": None,
        "jnotes": None,
        "shadecircles": None,
        "interpretcolors": None,
        "key": None,
        "hold": None,
        "track": None,
        "autowrap": None,
        "mini": None,
        "id": None,
        "id2": None,
        "code": None,
        "dow": "Friday",
        "type": None,
        "valid": True,
        "uniclue": False,
        "admin": False,
        "hastitle": False,
        "navigate": True,
        "auto": False,
        "size": {"rows": p.width, "cols": p.height},
        "grid": list(p.solution),
        "gridnums": gridnums,
        "circles": None,
        "acrossmap": None,
        "downmap": None,
        "rbars": None,
        "bbars": None,
        "clues": {
            "across": 
                across_clue_real,
            "down": 
                down_clue_real
        },
        "answers": {
            "across": across_answers,
            "down": down_answers
        }
    }
    # only print!
    print(json.dumps(crossword_data, indent=2))



    filename = str(filename_full) + ".json"

    with open(filename, 'w') as json_file:
        json.dump(crossword_data, json_file, indent=2)


    SUPABASE_URL = 'https://hetszssurnrltpueswfq.supabase.co'
    SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhldHN6c3N1cm5ybHRwdWVzd2ZxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDYyMTcwMDksImV4cCI6MjAyMTc5MzAwOX0.pcF2ejtrPQF73eC41eYBQ7mogLmQYEVCTbgTTbBC_E0'


    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    current_utc_time = datetime.now(timezone.utc)
    timestampz_format = current_utc_time.strftime('%Y-%m-%dT%H:%M:%S.%f%z')


    puzzle_id = str(uuid.uuid4())

    puzzle_data_supabase = {
        'id': puzzle_id,  # Replace with the actual UUID for the 'id' field
        'created_at': timestampz_format,  # Replace with the actual timestamp for the 'created_at' field
        'name': p.title,
        'rows': p.width,  # Replace with the actual value for the 'rows' field
        'cols': p.height,  # Replace with the actual value for the 'cols' field
        'grid': list(p.solution), 
        'gridnums': gridnums,  
        'circles': [],  
        'created_by': '839bbc36-c9a3-42b8-a0a4-0c86943cbce5', 
        'clues': {'down': down_clue_real, 'across': across_clue_real},  
        'answers': {'down': down_answers, 'across': across_answers},  
    }
    

    supabase.table('puzzles').upsert(puzzle_data_supabase).execute()
    




    # All done
    return p







# MAIN function END

def version_warn():
    ver = version.get_ver_from_github()
    

def main():
    
    url = "https://www.nytimes.com/crosswords/game/mini"
    browser = "Firefox"
  

    try:

        puzzle = get_puzzle(url, browser)
        output = data_to_puz(puzzle)

        

    except:
        print("ERROR!!!1! " * 10)
        import traceback
        traceback.print_exc()
        print("ERROR! " * 10)
        print("Settings: ", [browser, url, version.VERSION])


if __name__ == "__main__":

    main()