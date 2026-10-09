"""Application locale, sans dépendance externe. Base séparée, ouverte en lecture seule."""
import argparse
import csv
import io
import json
import sqlite3
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
SCHEMA_VERSION = 1


def connect(path):
    con = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    if con.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
        con.close()
        raise ValueError('Version de base non prise en charge. Utilisez une application compatible.')
    return con


def metadata(con):
    return [dict(r) for r in con.execute('''SELECT t.id,t.name,p.name park,
        MIN(s.timestamp) first,MAX(s.timestamp) last,COUNT(*) points,
        COUNT(s.wind) wind_points FROM turbines t JOIN parks p ON p.id=t.park_id
        JOIN samples s ON s.turbine_id=t.id GROUP BY t.id ORDER BY p.id,t.name''')]


def get_events(con, tid, start, end):
    return [dict(r) for r in con.execute('''SELECT id,kind,start,end,description,source FROM events
        WHERE (turbine_id=? OR turbine_id IS NULL) AND start<=? AND end>=? ORDER BY start''',
        (tid, end, start))]


def zones(rows, threshold, context_start):
    result, first, last = [], None, None
    def finish(resume=None):
        if first is not None and last is not None and last-first >= timedelta(hours=2):
            result.append({'start': first.isoformat(), 'mark': (first+timedelta(hours=2)).isoformat(),
                           'end': (resume or last).isoformat(),
                           'partial': first.isoformat()==context_start})
    for r in rows:
        t = datetime.fromisoformat(r['timestamp'])
        if last is not None and t-last > timedelta(minutes=10):
            finish(); first = last = None
        p = r['p']
        if p is not None and p <= threshold:
            if first is None:
                first = t
            last = t
        else:
            finish(t if p is not None else None)
            first = last = None
    finish()
    return result


def simplify(rows, target=1200):
    """Garde les points originaux extrêmes de chaque variable, et les ruptures."""
    if len(rows) <= 40000:
        return rows, False
    step = max(1, len(rows)//target)
    keep = {0, len(rows)-1}
    for a in range(0, len(rows), step):
        b = min(len(rows), a+step)
        keep.update((a,b-1))
        keep.update(i for i in range(a,b) if rows[i].get('break'))
        for key in ('p','q','wind'):
            indices = [i for i in range(a,b) if rows[i][key] is not None]
            if indices:
                keep.add(min(indices, key=lambda i:rows[i][key]))
                keep.add(max(indices, key=lambda i:rows[i][key]))
            for i in range(a,b):
                if rows[i][key] is None and (i==0 or rows[i-1][key] is not None):
                    keep.add(i)
                if rows[i][key] is not None and i>0 and rows[i-1][key] is None:
                    keep.add(i)
    return [rows[i] for i in sorted(keep)], True


def series(con, tid, start, end, threshold):
    if not con.execute('SELECT 1 FROM turbines WHERE id=?',(tid,)).fetchone():
        raise ValueError('Turbine inconnue')
    rows = [dict(r) for r in con.execute('''SELECT timestamp,p,q,wind FROM samples
        WHERE turbine_id=? AND timestamp>=? AND timestamp<=? ORDER BY timestamp''',(tid,start,end))]
    # Le début d'un arrêt peut précéder la fenêtre visible : retrouver le dernier point
    # qui interrompt l'arrêt, puis calculer sur les données brutes, avant simplification.
    previous = con.execute('''SELECT timestamp FROM samples WHERE turbine_id=? AND timestamp<?
        AND (p>? OR p IS NULL) ORDER BY timestamp DESC LIMIT 1''',(tid,start,threshold)).fetchone()
    lower = previous[0] if previous else con.execute(
        'SELECT MIN(timestamp) FROM samples WHERE turbine_id=?',(tid,)).fetchone()[0]
    context = [dict(r) for r in con.execute('''SELECT timestamp,p FROM samples WHERE turbine_id=?
        AND timestamp>=? AND timestamp<=? ORDER BY timestamp''',(tid,lower,end))]
    for i,row in enumerate(rows):
        row['break']=i>0 and datetime.fromisoformat(row['timestamp'])-datetime.fromisoformat(rows[i-1]['timestamp'])>timedelta(minutes=10)
    events = get_events(con,tid,start,end)
    found = [z for z in zones(context,threshold,lower) if z['end']>=start and z['mark']<=end]
    display, reduced = simplify(rows)
    return {'rows':display,'raw_count':len(rows),'simplified':reduced,'events':events,'zones':found,'chiro_total':con.execute("SELECT count(*) FROM events WHERE turbine_id=? AND kind='environment'",(tid,)).fetchone()[0],'chiro_first':con.execute("SELECT min(start) FROM events WHERE turbine_id=? AND kind='environment'",(tid,)).fetchone()[0]}


def handler(db):
    class Handler(BaseHTTPRequestHandler):
        def send(self, data, status=200, mime='application/json; charset=utf-8'):
            payload = json.dumps(data,ensure_ascii=False,allow_nan=False).encode() if mime.startswith('application/json') else data
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            u = urlparse(self.path)
            args = parse_qs(u.query)
            try:
                if u.path == '/api/meta':
                    with connect(db) as con:
                        data=metadata(con)
                    self.send({'turbines':data,'schema_version':SCHEMA_VERSION})
                elif u.path in ('/api/series','/api/export'):
                    tid=int(args['turbine'][0]); start=args['start'][0]; end=args['end'][0]
                    start=datetime.fromisoformat(start).isoformat(); end=datetime.fromisoformat(end).isoformat()
                    if start>end: raise ValueError('La date de fin doit suivre la date de début')
                    with connect(db) as con:
                        if u.path=='/api/series':
                            threshold=float(args.get('threshold',['10'])[0])
                            if not 0<=threshold<=100000:raise ValueError('Seuil invalide')
                            self.send(series(con,tid,start,end,threshold))
                        else:
                            output=io.StringIO(); writer=csv.writer(output,delimiter=';')
                            writer.writerow(['Horodatage','P Max (kW*)','Q Max (kvar*)','Vent moyen 10 min (m/s*)'])
                            for row in con.execute('SELECT timestamp,p,q,wind FROM samples WHERE turbine_id=? AND timestamp>=? AND timestamp<=? ORDER BY timestamp',(tid,start,end)):
                                writer.writerow([row[0],*['' if x is None else str(x).replace('.',',') for x in row[1:]]])
                            self.send(('\ufeff'+output.getvalue()).encode(),mime='text/csv; charset=utf-8')
                else:
                    file={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}.get(u.path)
                    if not file:self.send({'error':'Page introuvable'},404);return
                    mime={'html':'text/html','js':'text/javascript','css':'text/css'}[file.split('.')[-1]]+'; charset=utf-8'
                    self.send((ROOT/'static'/file).read_bytes(),mime=mime)
            except (ValueError,KeyError) as e:
                self.send({'error':str(e)},400)
            except Exception:
                self.send({'error':'Erreur de lecture. Consultez la console de l’application.'},500)
                import traceback;traceback.print_exc()

    return Handler


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',type=Path,default=ROOT.parent/'donnees'/'eolien.sqlite')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    if not args.db.is_file():parser.error('Base introuvable : '+str(args.db)+'. Placez la base dans le dossier donnees, ou utilisez --db.')
    with connect(args.db) as con:con.execute('SELECT 1 FROM samples LIMIT 1').fetchone()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(args.db))
    url=f'http://127.0.0.1:{args.port}'
    print('Explorateur éolien : '+url+'\nBase séparée : '+str(args.db.resolve())+'\nCtrl+C pour arrêter.')
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
