"""Import XLSX/CSV, bibliothèque standard uniquement. Base existante séparée."""
import argparse
import csv
import json
import math
import re
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def xlsx(path):
    with zipfile.ZipFile(path) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            shared=[''.join(node.itertext()) for node in root.findall('m:si',NS)]
        book=ET.fromstring(z.read('xl/workbook.xml'))
        rel=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        links={r.attrib['Id']:r.attrib['Target'] for r in rel}
        base=datetime(1904,1,1) if book.find('m:workbookPr',NS) is not None and book.find('m:workbookPr',NS).get('date1904') in ('1','true') else datetime(1899,12,30)
        for sheet in book.findall('m:sheets/m:sheet',NS):
            rid=sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target=links[rid];target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            rows=[]
            with z.open(target) as f:
                for _,node in ET.iterparse(f,events=('end',)):
                    if node.tag!= '{'+NS['m']+'}row':continue
                    values={}
                    for cell in node.findall('m:c',NS):
                        letters=re.match('[A-Z]+',cell.attrib['r']).group();col=0
                        for ch in letters:col=col*26+ord(ch)-64
                        raw=cell.find('m:v',NS);value=raw.text if raw is not None else None
                        kind=cell.get('t')
                        if kind=='s':value=shared[int(value)] if value is not None else None
                        elif kind=='inlineStr':value=''.join(cell.find('m:is',NS).itertext())
                        elif kind in ('str','d'):pass
                        elif kind=='e':value=None
                        elif value is not None:
                            try:value=float(value)
                            except ValueError:pass
                        values[col-1]=value
                    if values:rows.append([values.get(i) for i in range(max(values)+1)])
                    node.clear()
            yield sheet.attrib['name'],rows,base


def timestamp(value,base=datetime(1899,12,30)):
    if isinstance(value,(int,float)):
        return (base+timedelta(seconds=round(value*86400))).isoformat()
    value=str(value).strip()
    for fmt in ('%d/%m/%Y %H:%M:%S.%f','%d/%m/%Y %H:%M:%S','%d/%m/%Y %H:%M'):
        try:return datetime.strptime(value,fmt).isoformat()
        except ValueError:pass
    parsed=datetime.fromisoformat(value)
    if parsed.tzinfo:raise ValueError('Horodatage avec fuseau : harmonisez-le avec les données sources avant import.')
    return parsed.isoformat()


def number(value):
    if value in (None,''):return None
    result=float(str(value).replace(',','.'))
    return result if math.isfinite(result) else None


def unit(value,names):
    text=str(value).strip();match=re.search(r'([EA])\s*0*(\d+)$',text)
    if not match:raise ValueError('Turbine non reconnue : '+text)
    target=match.group(1)+str(int(match.group(2)))
    matches=[n for n in names if n[0]+str(int(n[1:]))==target]
    if len(matches)==1:return matches[0]
    if not matches:return match.group(1)+match.group(2).zfill(2) if match.group(1)=='E' else target
    raise ValueError('Turbine ambiguë : '+text)


def turbine(con,park,name):
    con.execute('INSERT OR IGNORE INTO turbines(park_id,name) VALUES (?,?)',(park,name))
    return con.execute('SELECT id FROM turbines WHERE park_id=? AND name=?',(park,name)).fetchone()[0]


def event(con,tid,kind,start,end,description,source):
    if end<start:raise ValueError('Fin antérieure au début : '+start)
    con.execute('INSERT OR IGNORE INTO events(turbine_id,kind,start,end,description,source) VALUES (?,?,?,?,?,?)',(tid,kind,start,end,description,source))


def import_file(con,file,parkname,kind='auto'):
    count=0
    if parkname:
        con.execute('INSERT OR IGNORE INTO parks(name) VALUES (?)',(parkname,))
        pid=con.execute('SELECT id FROM parks WHERE name=?',(parkname,)).fetchone()[0]
        names=[r[0] for r in con.execute('SELECT name FROM turbines WHERE park_id=?',(pid,))]
    else:pid=None;names=[]
    if file.suffix.lower()=='.xlsx':
        if not pid:raise ValueError('--park est obligatoire pour XLSX')
        for sheet,rows,base in xlsx(file):
            if not rows:continue
            header=[str(v or '').strip() for v in rows[0]];low=[h.lower() for h in header];source=file.name+' / '+sheet
            if 'pctimeStamp'.lower() in low:
                if kind not in ('auto','samples'):continue
                timecol=low.index('pctimestamp');columns=[]
                for c,h in enumerate(header):
                    if '_' not in h:continue
                    n=unit(h.split('_')[0],names)
                    field='wind' if 'WindSpeed Avg.' in h else 'q' if 'ReactivePower Max.' in h else 'p' if 'Production Power Max.' in h else None
                    if field:columns.append((c,turbine(con,pid,n),field))
                if not columns:continue
                for r in rows[1:]:
                    if timecol>=len(r) or r[timecol] is None:continue
                    time=timestamp(r[timecol],base);group={}
                    for c,tid,field in columns:group.setdefault(tid,{})[field]=number(r[c] if c<len(r) else None)
                    for tid,values in group.items():
                        # Les colonnes absentes ou vides n'effacent pas une mesure déjà importée.
                        con.execute('''INSERT INTO samples(turbine_id,timestamp,p,q,wind) VALUES (?,?,?,?,?)
                            ON CONFLICT(turbine_id,timestamp) DO UPDATE SET
                            p=COALESCE(excluded.p,samples.p),q=COALESCE(excluded.q,samples.q),wind=COALESCE(excluded.wind,samples.wind)''',
                            (tid,time,values.get('p'),values.get('q'),values.get('wind')))
                        count+=1
            elif all(h in low for h in ('unit','detected','device ack.')):
                if kind not in ('auto','harmonic'):continue
                idx={h:i for i,h in enumerate(low)}
                for r in rows[1:]:
                    r=r+[None]*max(0,len(header)-len(r));desc=str(r[idx.get('description',3)] or '')
                    remark=str(r[idx['remark']] or '') if 'remark' in idx else ''
                    if 'TempSwitch0GridFilter' not in (desc.strip(),remark.strip()):continue
                    if not r[idx['detected']] or not r[idx['device ack.']]:raise ValueError('Alarme sans début ou fin : '+source)
                    tid=turbine(con,pid,unit(r[idx['unit']],names))
                    event(con,tid,'harmonic',timestamp(r[idx['detected']],base),timestamp(r[idx['device ack.']],base),desc,source);count+=1
    elif file.suffix.lower()=='.csv':
        if kind not in ('price','environment'):raise ValueError('CSV : indiquez --kind price ou --kind environment')
        if kind=='environment' and not pid:raise ValueError('--park est obligatoire pour les bridages')
        for r in csv.DictReader(file.open(encoding='utf-8-sig'),delimiter=';'):
            if not r.get('Date détection') or not r.get('Date reset'):raise ValueError('Événement sans début ou fin')
            tid=None
            if kind=='environment':
                # L'import est explicitement lié au parc --park, jamais deviné sur le nom de turbine.
                tid=turbine(con,pid,unit(list(r.values())[1],names))
            event(con,tid,kind,timestamp(r['Date détection']),timestamp(r['Date reset']),r.get('Sous-Catégorie',kind),file.name);count+=1
    else:raise ValueError('Format accepté : XLSX ou CSV')
    if count==0:raise ValueError('Aucune donnée compatible trouvée ; rien importé.')
    con.execute('INSERT INTO imports(source,imported_at,details) VALUES (?,?,?)',(file.name,datetime.now().isoformat(),json.dumps({'park':parkname,'kind':kind,'processed':count},ensure_ascii=False)))
    return count


if __name__=='__main__':
    p=argparse.ArgumentParser(description='Import dans une base existante. Arrêtez le serveur avant import.')
    p.add_argument('file',type=Path);p.add_argument('--db',type=Path,default=Path(__file__).resolve().parent.parent/'donnees'/'eolien.sqlite')
    p.add_argument('--park');p.add_argument('--kind',choices=['auto','samples','harmonic','price','environment'],default='auto');args=p.parse_args()
    if not args.db.is_file() or not args.file.is_file():p.error('Base ou fichier introuvable')
    con=sqlite3.connect(args.db)
    if con.execute('PRAGMA user_version').fetchone()[0]!=1:p.error('Version de base non prise en charge')
    backup=args.db.with_name(args.db.stem+'_sauvegarde_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.sqlite')
    with sqlite3.connect(backup) as dest:con.backup(dest)
    try:
        with con:count=import_file(con,args.file,args.park,args.kind)
        print(str(count)+' lignes traitées. Sauvegarde : '+str(backup))
    except Exception as e:
        print('Import annulé, base conservée : '+str(e));raise SystemExit(1)
    finally:con.close()
