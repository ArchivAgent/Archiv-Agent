from __future__ import annotations
import csv, json, os, re, ssl, subprocess, sys, traceback, faulthandler, urllib.parse, urllib.request, xml.etree.ElementTree as ET
import certifi
from pathlib import Path
from archivagent.image_import import import_image_files
from PySide6.QtCore import Qt, QThread, QUrl, QObject, Signal, Slot, QRectF, QTimer, QPointF
from PySide6.QtGui import QAction, QDesktopServices, QFont, QPixmap, QPen, QColor, QTextCursor, QTextCharFormat, QTextDocument, QPainter, QBrush, QPolygonF
from PySide6.QtWidgets import (QApplication,QCheckBox,QComboBox,QDoubleSpinBox,QFileDialog,QFormLayout,QFrame,QGridLayout,QGroupBox,QHBoxLayout,QLabel,QLineEdit,QListWidget,QMainWindow,QMessageBox,QPlainTextEdit,QTextEdit,QProgressBar,QPushButton,QSpinBox,QSplitter,QStackedWidget,QTableWidget,QTableWidgetItem,QToolBar,QVBoxLayout,QWidget,QGraphicsView,QGraphicsScene,QGraphicsPixmapItem,QGraphicsRectItem,QGraphicsItem,QHeaderView,QMenu,QAbstractSpinBox)

XLINK='{http://www.w3.org/1999/xlink}href'
def installed_app_dir():
    if getattr(sys,'frozen',False):
        return Path(sys.executable).resolve().parent
    return Path(os.environ.get('ARCHIVAGENT_HOME',r'C:\ArchivAgent'))
BASE_DEFAULT=str(installed_app_dir())

def safe_name(s):
    s=re.sub(r'[<>:"/\\|?*]+','_',s); s=re.sub(r'\s+',' ',s).strip(' ._'); return s[:160] or 'Unbenannt'
def request_bytes(url):
    req=urllib.request.Request(url,headers={'User-Agent':'ArchivAgent/7.0','Accept':'*/*'})
    context=ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req,timeout=120,context=context) as r:
        return r.read()
def extract_mets_url(url):
    url=url.strip()
    if not url: raise ValueError('Der Link zum Kirchenbuch ist leer.')
    parsed=urllib.parse.urlparse(url); q=urllib.parse.parse_qs(parsed.query)
    for key in ('tx_dlf[id]','id'):
        for c in q.get(key,[]):
            c=urllib.parse.unquote(c)
            if c.startswith(('http://','https://')): return c
    d=urllib.parse.unquote(url)
    m=re.search(r'(https?://[^&\s]+?(?:mets[^&\s]*?xml|mets\?id=[^&\s]+))',d,re.I)
    if m:return m.group(1)
    if 'mets' in d.casefold() and d.startswith(('http://','https://')):return d
    raise ValueError('Im Link wurde keine METS-Adresse gefunden.')
def score_group(v):
    v=v.casefold()
    for n,s in [('original',100),('master',95),('max',90),('full',85),('default',80),('image',70),('thumb',10)]:
        if n in v:return s
    return 50
def image_urls(xml_data,base):
    root=ET.fromstring(xml_data); groups=[]
    for g in root.findall('.//{*}fileGrp'):
        urls=[]
        for f in g.findall('.//{*}FLocat'):
            h=f.attrib.get(XLINK) or f.attrib.get('href')
            if h:urls.append(urllib.parse.urljoin(base,h))
        if urls:groups.append((score_group(g.attrib.get('USE','')),urls))
    groups.sort(key=lambda x:x[0],reverse=True)
    if not groups:raise RuntimeError('Keine Bildadressen in METS gefunden.')
    out=[]
    for u in groups[0][1]:
        if u not in out:out.append(u)
    return out
def ext(url):
    s=Path(urllib.parse.urlparse(url).path).suffix.lower(); return s if s in {'.jpg','.jpeg','.png','.tif','.tiff','.jp2','.webp'} else '.jpg'
def find_images(d):
    ex={'.jpg','.jpeg','.png','.tif','.tiff','.jp2','.webp'}; out=[]
    for f in (d/'Originalseiten',d/'Scans',d):
        if f.exists():out += [p for p in f.iterdir() if p.is_file() and p.suffix.lower() in ex]
    return sorted(set(out))
def image_page_number(path):
    """Liest die echte Buchseite aus Namen wie Seite_0020_0020.jpg."""
    m=re.search(r'(?:Seite|Viewer)[_-]?(\d+)',path.stem,re.I)
    if m:return int(m.group(1))
    numbers=re.findall(r'\d+',path.stem)
    return int(numbers[0]) if numbers else None
def read_hits(pd):
    hits=[]
    if not pd.exists():return hits
    ignored={'sicherung','backup','backups','archiv','archive'}
    candidates=list(pd.rglob('*.csv'))+list(pd.rglob('*.tsv'))
    paths=sorted([p for p in candidates if not any(part.casefold() in ignored for part in p.relative_to(pd).parts[:-1])],key=lambda p:p.stat().st_mtime,reverse=True)
    for path in paths:
        try:
            text=path.read_text(encoding='utf-8-sig',errors='replace'); lines=text.splitlines()
            if not lines: continue
            # ArchivAgent-Ergebnisdateien verwenden meist Semikolon. Kommas stehen
            # dagegen häufig innerhalb des Trefferfeldes und dürfen nicht als
            # Spaltentrenner interpretiert werden.
            header=lines[0]
            if path.suffix.lower()=='.tsv' or '\t' in header:
                delimiter='\t'
            elif ';' in header:
                delimiter=';'
            else:
                delimiter=','
            for row in csv.DictReader(lines,delimiter=delimiter):
                n={str(k or '').strip().casefold():str(v or '').strip() for k,v in row.items()}
                def pick(*ks):
                    for k in ks:
                        if n.get(k):return n[k]
                    return ''
                # Exaktes Schema der gemeinsamen ArchivAgent-Trefferliste:
                # buchtitel;seite;suchname;erkannt;aehnlichkeit;methode;zeile;kontext;bilddatei;textdatei
                raw_names=pick('name','treffer','familienname','wort','match','gefunden','erkannt')
                if not raw_names or raw_names=='-':continue
                # Mehrere gefundene Namen werden als einzelne Tabellenzeilen gezeigt.
                names=[x.strip() for x in re.split(r'[,;|]+',raw_names) if x.strip() and x.strip()!='-']
                if not names:continue
                try:
                    rel=path.relative_to(pd)
                    inferred_book=rel.parts[0] if len(rel.parts)>1 else ''
                except Exception:
                    inferred_book=''
                common={'book':pick('buch','book','buchtitel') or inferred_book,'page':pick('seite','page','dfg-seite','dfg_seite'),'confidence':pick('sicherheit','confidence','score','ähnlichkeit','aehnlichkeit'),'context':pick('kontext','context','ocr','text'),'image':pick('bild','image','scan','datei','file','bilddatei'),'x':pick('x','left','bbox_x'),'y':pick('y','top','bbox_y'),'w':pick('w','width','breite','bbox_w'),'h':pick('h','height','höhe','bbox_h'),'line':pick('zeile','line','line_no','zeilennummer'),'textfile':pick('textdatei','textfile','ocrdatei'),'source':str(path)}
                for name in names:
                    if name.casefold().startswith('fehler:'):continue
                    hits.append({'name':name,**common})
        except Exception:
            pass
    return hits



class Worker(QObject):
    log=Signal(str); progress=Signal(int,int); stage=Signal(str); finished=Signal(bool,str)
    def __init__(self,action,p):super().__init__();self.action=action;self.p=p;self.cancelled=False;self.proc=None
    def cancel(self):
        self.cancelled=True
        if self.proc and self.proc.poll() is None:self.proc.terminate()
    def run(self):
        try:
            if self.action in ('download','all'):self.download()
            if not self.cancelled and self.action in ('htr','all'):self.htr()
            self.finished.emit(not self.cancelled,'Vorgang abgeschlossen.' if not self.cancelled else 'Vorgang abgebrochen.')
        except Exception as e:self.finished.emit(False,str(e))
    def download(self):
        base=Path(self.p['base']); project=safe_name(self.p['project']); book=safe_name(self.p['book']); viewer=self.p['url'].strip(); mets=extract_mets_url(viewer)
        self.log.emit('[METS] '+mets); xml=request_bytes(mets); urls=image_urls(xml,mets)
        bd=base/'Projekte'/project/book; out=bd/'Originalseiten'; out.mkdir(parents=True,exist_ok=True)
        (bd/'mets.xml').write_bytes(xml); (bd/'quelle.txt').write_text(f'DFG-Viewer:\n{viewer}\n\nMETS:\n{mets}\n',encoding='utf-8')
        start=max(1,int(self.p.get('start',1)))
        end=int(self.p.get('end',0) or 0)
        last=len(urls) if end==0 else min(end,len(urls))
        if start>len(urls) or start>last:
            raise RuntimeError(f'Der Seitenbereich {start} bis {end or "Ende"} liegt außerhalb des Buches mit {len(urls)} Seiten.')
        selected_urls=urls[start-1:last]
        total=len(selected_urls)
        self.stage.emit(f'Download: {total} Seite(n) werden vorbereitet')
        self.log.emit(f'[DOWNLOAD-BEREICH] Seiten {start} bis {last} ({total} Seite(n))')
        for done,(i,u) in enumerate(enumerate(selected_urls,start),1):
            if self.cancelled:return
            t=out/f'Seite_{i:04d}_{i:04d}{ext(u)}'
            if t.exists() and t.stat().st_size>10000:
                self.log.emit(f'[{i:04d}] vorhanden: {t.name}')
            else:
                self.log.emit(f'[{i:04d}] lade: {t.name}')
                t.write_bytes(request_bytes(u))
            self.progress.emit(done,total)
        self.log.emit(f'[DOWNLOAD] Fertig: {total} Seite(n), Bereich {start} bis {last}.')
    def htr(self):
        base=Path(self.p['base']); py=base/'runtime'/'Scripts'/'python.exe'; script=base/'archiv_agent.py'
        if not py.exists():raise RuntimeError(f'Nicht gefunden: {py}')
        if not script.exists():raise RuntimeError(f'Nicht gefunden: {script}')
        # Vorab ausschließlich echte Bilddateien bestimmen. TXT-Dateien sind OCR-Ausgaben,
        # werden aber niemals als Eingabeseiten verwendet.
        book_dir=base/'Projekte'/safe_name(self.p['project'])/safe_name(self.p['book'])
        images=find_images(book_dir)
        start=max(1,int(self.p['start']))
        end=int(self.p.get('end',0) or 0)
        numbered=[(image_page_number(img),img) for img in images]
        selected=[img for page,img in numbered if page is not None and page>=start and (end==0 or page<=end)]
        # Für fremd benannte Altbestände ohne erkennbare Seitennummer bleibt
        # die bisherige positionsbezogene Auswahl als Rückfall erhalten.
        if not selected and images and all(page is None for page,_ in numbered):
            selected=images[start-1:]
            if self.p['limit']>0:selected=selected[:self.p['limit']]
        if not selected:
            available=', '.join(str(page) for page,_ in numbered if page is not None) or 'keine erkennbaren Seitennummern'
            raise RuntimeError(f'Für den Seitenbereich {start} bis {end or "Ende"} wurden keine passenden Bilder gefunden. Vorhandene Seiten: {available}. Ordner: {book_dir}')
        self.log.emit(f'[BILDER] Gefunden: {len(images)} echte Bilddatei(en); ausgewählt: {len(selected)}')
        for img in selected:self.log.emit(f'[AUSWAHL {image_page_number(img) or "?"}] {img.name}')
        self.progress.emit(0,len(selected))
        self.stage.emit(f'Texterkennung wird vorbereitet – {len(selected)} Seite(n)')

        # Mit der tatsächlich installierten Backend-Version kompatibel bleiben.
        try:
            help_text=subprocess.check_output([str(py),str(script),'--help'],cwd=base,text=True,encoding='utf-8',errors='replace',creationflags=(subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
        except Exception:
            help_text=''
        mode='--htr' if '--htr' in help_text else '--ocr'
        cmd=[str(py),'-u',str(script),mode,'--projekt',self.p['project'],'--buch',self.p['book'],'--start',str(start),'--limit',str(len(selected))]
        if self.p.get('names') and '--names' in help_text:
            cmd += ['--names'] + [n.strip() for n in re.split(r'[,;]+', self.p['names']) if n.strip()]
        if '--schwelle' in help_text:cmd += ['--schwelle',str(self.p['threshold'])]
        if self.p['force'] and '--force' in help_text:cmd.append('--force')
        self.log.emit(f'[MODUS] Backend verwendet {mode}')
        self.log.emit('[TEXTERKENNUNG] '+subprocess.list2cmdline(cmd)); env=os.environ.copy();env.update(PYTHONUNBUFFERED='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        self.proc=subprocess.Popen(cmd,cwd=base,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=flags)
        current_page=''; current_image=''
        for line in self.proc.stdout:
            if self.cancelled:return
            text=line.rstrip(); self.log.emit(text)
            protocol=re.match(r'\[HTR (START|FERTIG) (\d+)/(\d+)\]\s+Seite\s+(\d+):?\s*(.*)',text,re.I)
            if protocol:
                state,index,total,page,detail=protocol.groups()
                index=int(index);total=int(total)
                if state.casefold()=='start':
                    self.progress.emit(index-1,total)
                    self.stage.emit(f'Texterkennung: Seite {page} wird gelesen – {index} von {total}')
                else:
                    self.progress.emit(index,total)
                    self.stage.emit(f'Texterkennung: Seite {page} fertig – {index} von {total}')
                continue
            # Seitenmeldungen verschiedener Backend-Versionen erkennen, z. B.
            # [OCR 0021] Seite_0021.jpg, [HTR 21/100] ..., Seite 21 ...
            m=re.search(r'\[(?:OCR|HTR)[^\d]*(\d+)(?:\s*/\s*(\d+))?\]\s*(.*)',text,re.I)
            if not m:
                m=re.search(r'\b(?:Seite|Page)\s*[:#-]?\s*(\d+)(?:\s*/\s*(\d+))?\b\s*(.*)',text,re.I)
            if m:
                current_page=m.group(1); current_image=(m.group(3) or '').strip()
                try:
                    done=max(1, int(current_page)-int(self.p['start'])+1)
                    total=self.p['limit'] if self.p['limit']>0 else max(done,1)
                    self.progress.emit(done,total)
                except Exception:
                    pass
            # Treffer werden bewusst erst nach Abschluss aus den Ergebnisdateien geladen.
        code=self.proc.wait()
        if self.cancelled:
            self.log.emit('[ABBRUCH] Texterkennung wurde vom Benutzer beendet.')
            return
        if code:raise RuntimeError(f'HTR endete mit Fehlercode {code}.')

class MovableMarker(QGraphicsRectItem):
    """Verschiebbare und an Kanten/Ecken skalierbare Treffermarkierung."""
    HANDLE_MARGIN = 14.0
    MIN_WIDTH = 30.0
    MIN_HEIGHT = 16.0

    def __init__(self, rect, changed_callback=None):
        super().__init__(rect)
        self.changed_callback=changed_callback
        self.resize_handle=None
        self.resize_start_rect=None
        self.resize_start_scene_pos=None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges,True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def itemChange(self,change,value):
        result=super().itemChange(change,value)
        if change==QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.changed_callback:
            self.changed_callback()
        return result

    def _handle_at(self,pos):
        r=self.rect();m=self.HANDLE_MARGIN
        left=abs(pos.x()-r.left())<=m;right=abs(pos.x()-r.right())<=m
        top=abs(pos.y()-r.top())<=m;bottom=abs(pos.y()-r.bottom())<=m
        inside_x=r.left()-m<=pos.x()<=r.right()+m
        inside_y=r.top()-m<=pos.y()<=r.bottom()+m
        if top and left:return 'tl'
        if top and right:return 'tr'
        if bottom and left:return 'bl'
        if bottom and right:return 'br'
        if left and inside_y:return 'l'
        if right and inside_y:return 'r'
        if top and inside_x:return 't'
        if bottom and inside_x:return 'b'
        return None

    def _set_handle_cursor(self,handle):
        cursors={
            'tl':Qt.CursorShape.SizeFDiagCursor,'br':Qt.CursorShape.SizeFDiagCursor,
            'tr':Qt.CursorShape.SizeBDiagCursor,'bl':Qt.CursorShape.SizeBDiagCursor,
            'l':Qt.CursorShape.SizeHorCursor,'r':Qt.CursorShape.SizeHorCursor,
            't':Qt.CursorShape.SizeVerCursor,'b':Qt.CursorShape.SizeVerCursor,
        }
        self.setCursor(cursors.get(handle,Qt.CursorShape.SizeAllCursor))

    def hoverMoveEvent(self,event):
        self._set_handle_cursor(self._handle_at(event.pos()))
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self,event):
        if not self.resize_handle:self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            handle=self._handle_at(event.pos())
            if handle:
                self.resize_handle=handle
                self.resize_start_rect=self.sceneBoundingRect()
                self.resize_start_scene_pos=event.scenePos()
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,False)
                event.accept();return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if not self.resize_handle or self.resize_start_rect is None:
            super().mouseMoveEvent(event);return
        delta=event.scenePos()-self.resize_start_scene_pos
        r=QRectF(self.resize_start_rect)
        h=self.resize_handle
        left,right,top,bottom=r.left(),r.right(),r.top(),r.bottom()
        if 'l' in h:left=min(left+delta.x(),right-self.MIN_WIDTH)
        if 'r' in h:right=max(right+delta.x(),left+self.MIN_WIDTH)
        if 't' in h:top=min(top+delta.y(),bottom-self.MIN_HEIGHT)
        if 'b' in h:bottom=max(bottom+delta.y(),top+self.MIN_HEIGHT)
        self.prepareGeometryChange()
        self.setPos(left,top)
        self.setRect(QRectF(0,0,right-left,bottom-top))
        if self.changed_callback:self.changed_callback()
        event.accept()

    def mouseReleaseEvent(self,event):
        if self.resize_handle:
            self.resize_handle=None;self.resize_start_rect=None;self.resize_start_scene_pos=None
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,True)
            self._set_handle_cursor(self._handle_at(event.pos()))
            if self.changed_callback:self.changed_callback()
            event.accept();return
        super().mouseReleaseEvent(event)

class ScanView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene=QGraphicsScene(self);self.setScene(self.scene)
        self.pix=None;self.source_pm=None;self.rect=None;self.rotation=0
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QColor('#20252a'))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.save_marker_callback=None;self.reset_marker_callback=None;self.marker_changed_callback=None
        self.min_zoom=0.5;self.max_zoom=8.0;self.overview_zoom=0.5

    def show_image(self,path,bbox=None):
        self.scene.clear();self.pix=None;self.source_pm=None;self.rect=None;self.rotation=0
        pm=QPixmap(str(path))
        if pm.isNull():return False
        self.source_pm=pm;self.pix=self.scene.addPixmap(pm)
        if bbox:
            x,y,w,h=bbox;pen=QPen(QColor('#e53935'));pen.setWidth(5)
            self.rect=MovableMarker(QRectF(0,0,w,h),self._marker_changed);self.rect.setPos(x,y);self.rect.setPen(pen);self.rect.setBrush(QColor(255,207,51,65));self.rect.setZValue(10);self.scene.addItem(self.rect)
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        # Einheitliche Übersicht: 50 % und Trefferstelle zentriert.
        self.resetTransform();self.scale(self.overview_zoom,self.overview_zoom)
        if self.rect:self.centerOn(self.rect.sceneBoundingRect().center())
        else:self.centerOn(self.pix.sceneBoundingRect().center())
        return True

    def marker_bbox(self):
        if not self.rect:return None
        r=self.rect.sceneBoundingRect();return (r.x(),r.y(),r.width(),r.height())

    def _marker_changed(self):
        if self.marker_changed_callback:
            self.marker_changed_callback()

    def mousePressEvent(self,event):
        # Strg + Linksklick setzt die Markierung sofort und speichert sie.
        if (event.button()==Qt.MouseButton.LeftButton and
                event.modifiers() & Qt.KeyboardModifier.ControlModifier and self.rect):
            p=self.mapToScene(event.position().toPoint())
            r=self.rect.rect()
            self.rect.setPos(p.x()-r.width()/2,p.y()-r.height()/2)
            if self.save_marker_callback:self.save_marker_callback()
            event.accept();return
        super().mousePressEvent(event)

    def contextMenuEvent(self,event):
        if not self.rect:
            super().contextMenuEvent(event);return
        menu=QMenu(self)
        save=menu.addAction('Trefferposition speichern')
        reset=menu.addAction('Automatische Position wiederherstellen')
        chosen=menu.exec(event.globalPos())
        if chosen==save and self.save_marker_callback:self.save_marker_callback()
        elif chosen==reset and self.reset_marker_callback:self.reset_marker_callback()

    def enterEvent(self,event):
        super().enterEvent(event);self.setFocus(Qt.FocusReason.MouseFocusReason)

    def set_zoom(self,value):
        value=max(self.min_zoom,min(self.max_zoom,float(value)))
        current=abs(self.transform().m11()) or 1.0
        self.scale(value/current,value/current)

    def zoom_in(self):self.set_zoom(abs(self.transform().m11())*1.25)
    def zoom_out(self):self.set_zoom(abs(self.transform().m11())/1.25)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.pix:
            current=abs(self.transform().m11())
            self.set_zoom(1.0 if abs(current-self.overview_zoom)<0.08 else self.overview_zoom)
            event.accept();return
        super().mouseDoubleClickEvent(event)
    def wheelEvent(self,event):
        delta=event.angleDelta().y()
        if not delta:event.ignore();return
        factor=1.18 if delta>0 else 1/1.18;current=abs(self.transform().m11());target=current*factor
        if self.min_zoom <= target <= self.max_zoom:self.scale(factor,factor)
        elif target<self.min_zoom:self.set_zoom(self.min_zoom)
        else:self.set_zoom(self.max_zoom)
        event.accept()

    def fit(self):
        if self.pix:self.fitInView(self.pix,Qt.AspectRatioMode.KeepAspectRatio)
    def rotate_right(self):
        if self.pix:self.rotation=(self.rotation+90)%360;self.pix.setRotation(self.rotation);self.scene.setSceneRect(self.scene.itemsBoundingRect());self.fit()

class ReadingArchivist(QWidget):
    """Kleine, vollständig lokal gezeichnete Leseanimation."""
    def __init__(self,parent=None):
        super().__init__(parent);self.frame=0;self.completed=False;self.setFixedHeight(72);self.setMinimumWidth(240)
        self.timer=QTimer(self);self.timer.setInterval(180);self.timer.timeout.connect(self.advance)
        self.hide()
    def start(self):
        self.completed=False;self.show()
        if not self.timer.isActive():self.timer.start()
        self.update()
    def stop(self):
        self.timer.stop();self.completed=False;self.hide()
    def finish(self):
        self.timer.stop();self.completed=True;self.show();self.update()
    def advance(self):
        self.frame=(self.frame+1)%24;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x=max(12,(self.width()-190)//2);bob=1 if self.frame%6 in (1,2) else 0
        # Tisch und Schatten
        p.setPen(QPen(QColor('#8b6b47'),3));p.drawLine(x+14,61,x+176,61)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(0,0,0,25));p.drawEllipse(x+32,59,125,7)
        # Körper und Kapuze des Archivarius
        p.setBrush(QColor('#6b4f3a'));p.drawRoundedRect(x+55,31+bob,58,31,10,10)
        p.setBrush(QColor('#4d382c'));p.drawEllipse(x+62,5+bob,43,39)
        p.setBrush(QColor('#e8c39e'));p.drawEllipse(x+69,11+bob,29,27)
        # Augen wandern über die Buchzeilen
        eye_shift=(self.frame//3)%3
        p.setBrush(QColor('#263238'));p.drawEllipse(x+77+eye_shift,22+bob,3,3);p.drawEllipse(x+88+eye_shift,22+bob,3,3)
        # Aufgeschlagenes Buch
        left=QPolygonF([QPointF(x+20,39),QPointF(x+66,35),QPointF(x+78,58),QPointF(x+31,60)])
        right=QPolygonF([QPointF(x+78,58),QPointF(x+90,35),QPointF(x+139,39),QPointF(x+126,60)])
        p.setPen(QPen(QColor('#9a7448'),1));p.setBrush(QColor('#fff4cf'));p.drawPolygon(left);p.drawPolygon(right)
        p.setPen(QPen(QColor('#b8a781'),1))
        for dy in (43,47,51):p.drawLine(x+34,dy,x+67,dy-2);p.drawLine(x+91,dy-2,x+126,dy)
        p.setPen(QPen(QColor('#8b6b47'),1));p.drawLine(x+78,38,x+78,58)
        # Feder bewegt sich beim Lesen; gelegentlich hebt sich eine Buchseite.
        quill_y=34+(self.frame%4);p.setPen(QPen(QColor('#34515e'),2));p.drawLine(x+132,quill_y,x+153,16+quill_y//8)
        p.setBrush(QColor('#607d8b'));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(x+147,15+quill_y//8,14,5)
        if 18<=self.frame<=22:
            page=QPolygonF([QPointF(x+78,57),QPointF(x+91,35),QPointF(x+112-(self.frame-18)*7,31),QPointF(x+78,57)])
            p.setBrush(QColor('#fff9df'));p.setPen(QPen(QColor('#c5ad7b'),1));p.drawPolygon(page)
        if self.completed:
            p.setBrush(QColor('#2e9d55'));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(x+157,15,25,25)
            p.setPen(QPen(Qt.GlobalColor.white,3));p.drawLine(x+163,27,x+169,33);p.drawLine(x+169,33,x+178,22)


class Main(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('ArchivAgent 7.0 RC2');self.resize(1220,800);self.setMinimumSize(980,680);self.thread=None;self.worker=None;self.pending_result=None;self.current_image_index=-1;self.current_images=[];self.current_hit=None;self.current_auto_bbox=None;self.current_position_key=None;self.all_hit_rows=[];self.hit_ratings={};self.last_rating_action=None
        self.base=QLineEdit(BASE_DEFAULT);self.project=QComboBox();self.project.setEditable(True);self.book=QComboBox();self.book.setEditable(True);self.url=QLineEdit();self.names=QLineEdit();self.start=QSpinBox();self.start.setRange(1,999999);self.start.setValue(1);self.start.setSingleStep(1);self.start.setAccelerated(True);self.start.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons);self.end=QSpinBox();self.end.setRange(0,999999);self.end.setValue(0);self.end.setSingleStep(1);self.end.setAccelerated(True);self.end.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons);self.threshold=QDoubleSpinBox();self.threshold.setRange(.5,1);self.threshold.setValue(.72);self.threshold.setSingleStep(.01);self.threshold.setDecimals(2);self.threshold.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons);self.force=QCheckBox('Vorhandene Texterkennung erneut ausführen');self.log=QPlainTextEdit();self.log.setReadOnly(True);self.progress=QProgressBar();self.stats={};self.hit_rows=[];self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['Status','Name','Buch','Seite','Übereinstimmung','Textumgebung','Quelle']);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.scan_view=ScanView();self.scan_view.save_marker_callback=self.save_current_marker;self.scan_view.reset_marker_callback=self.reset_current_marker;self.scan_view.marker_changed_callback=self.marker_moved;self.scan_title=QLabel('Kein Treffer ausgewählt');self.scan_title.setWordWrap(True);self.page_label=QLabel('Seite – / –');self.ocr_title=QLabel('Erkannter Text');self.ocr_title.setFont(QFont('Segoe UI',11,QFont.Weight.Bold));self.ocr_text=QTextEdit();self.ocr_text.setReadOnly(True);self.ocr_text.setPlaceholderText('Zu diesem Treffer wurde noch kein erkannter Text gefunden.');self.ocr_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth);self.book_table=QTableWidget(0,5);self.book_table.setHorizontalHeaderLabels(['Buch','Seiten','Heruntergeladen','Text erkannt','Treffer']);self.book_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.nav=QListWidget();self.nav.addItems(['Buch durchsuchen','Bücher','Treffer prüfen','Übersicht','Statistik','Einstellungen']);self.nav.setFixedWidth(220);self.stack=QStackedWidget()
        for w in [self.search_page(),self.books_page(),self.hits_page(),self.dashboard(),self.statistics_page(),self.settings_page()]:self.stack.addWidget(w)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex);self.nav.currentRowChanged.connect(lambda _:self.refresh())
        sp=QSplitter();sp.addWidget(self.nav);sp.addWidget(self.stack);sp.setStretchFactor(1,1);self.setCentralWidget(sp);self.toolbar();self.style();self.refresh();self.nav.setCurrentRow(0)
    def head(self,t,s):
        w=QWidget();l=QVBoxLayout(w);h=QLabel(t);h.setFont(QFont('Segoe UI',22,QFont.Weight.Bold));x=QLabel(s);x.setWordWrap(True);l.addWidget(h);l.addWidget(x);return w
    def select_box(self):
        g=QGroupBox('Auswahl');f=QFormLayout(g);f.addRow('Projekt',self.project);f.addRow('Buch',self.book);self.project.currentTextChanged.connect(self.refresh_books);return g
    def dashboard(self):
        w=QWidget();l=QVBoxLayout(w);l.addWidget(self.head('ArchivAgent 7.0 RC2','Online-Archive und eigene Scans lesen, nach Familiennamen suchen und Ergebnisse prüfen.'));g=QGridLayout()
        for i,k in enumerate(['Projekte','Bücher','Scans','Treffer']):
            c=QFrame();c.setObjectName('card');cl=QVBoxLayout(c);a=QLabel(k);a.setFont(QFont('Segoe UI',12,QFont.Weight.Bold));v=QLabel('0');v.setFont(QFont('Segoe UI',25,QFont.Weight.Bold));self.stats[k]=v;cl.addWidget(a);cl.addWidget(v);g.addWidget(c,i//2,i%2)
        l.addLayout(g);l.addStretch();return w
    def search_page(self):
        w=QWidget();l=QVBoxLayout(w)
        l.addWidget(self.head('Buch durchsuchen','Buchseiten herunterladen, Schrift erkennen und nach Familiennamen durchsuchen.'))
        g=QGroupBox('Suchmaske');f=QFormLayout(g)
        f.addRow('Projekt',self.project)
        f.addRow('Buch',self.book)
        self.project.currentTextChanged.connect(self.refresh_books)
        f.addRow('Familienname(n)',self.names)
        f.addRow('Suchgenauigkeit',self.threshold_spin_controls())
        accuracy_hint=QLabel('Empfehlung: 0,85. Höher = weniger falsche Treffer; niedriger = empfindlichere Suche.');accuracy_hint.setWordWrap(True);f.addRow('',accuracy_hint)
        lr=QHBoxLayout();lr.addWidget(self.url)
        pb=QPushButton('Link aus Zwischenablage');pb.clicked.connect(lambda:self.url.setText(QApplication.clipboard().text().strip()));lr.addWidget(pb)
        f.addRow('Link zum Kirchenbuch',lr)
        sr=QHBoxLayout()
        sr.addWidget(QLabel('Von Seite'))
        sr.addLayout(self.page_spin_controls(self.start, 1))
        sr.addSpacing(18)
        sr.addWidget(QLabel('Bis Seite'))
        sr.addLayout(self.page_spin_controls(self.end, 0))
        sr.addStretch()
        f.addRow('Seitenbereich',sr)
        page_hint=QLabel('Hinweis: 0 bei „Bis Seite“ = bis zum Ende des Buches.');page_hint.setWordWrap(True);f.addRow('',page_hint)
        f.addRow('',self.force)
        hint=QLabel('Mehrere Familiennamen bitte mit Komma trennen, zum Beispiel: Müller, Huber, Schmidt.');hint.setWordWrap(True);f.addRow('',hint)
        l.addWidget(g)
        r=QHBoxLayout()
        a=QPushButton('Alles automatisch starten');a.setObjectName('primary');a.clicked.connect(lambda:self.start_task('all'))
        h=QPushButton('Vorhandenes Buch durchsuchen');h.clicked.connect(lambda:self.start_task('htr'))
        d=QPushButton('Nur Seiten herunterladen');d.clicked.connect(lambda:self.start_task('download'))
        i=QPushButton('Eigene Scans/Bilder hinzufügen');i.clicked.connect(self.import_own_images)
        c=QPushButton('Abbrechen');c.clicked.connect(self.cancel)
        r.addWidget(a);r.addWidget(h);r.addWidget(d);r.addWidget(i);r.addWidget(c);r.addStretch();l.addLayout(r)
        l.addWidget(self.task_panel())
        return w


    def threshold_spin_controls(self):
        """Trefferschwelle mit eigenen, zuverlässig funktionierenden Pfeiltasten."""
        box=QHBoxLayout();box.setSpacing(0)
        self.threshold.setMinimumWidth(120)
        box.addWidget(self.threshold)
        buttons=QVBoxLayout();buttons.setSpacing(0);buttons.setContentsMargins(2,0,0,0)
        up=QPushButton('▲');down=QPushButton('▼')
        for button in (up,down):
            button.setFixedSize(30,22);button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        up.clicked.connect(self.threshold.stepUp)
        down.clicked.connect(self.threshold.stepDown)
        buttons.addWidget(up);buttons.addWidget(down)
        box.addLayout(buttons);box.addStretch()
        return box

    def page_spin_controls(self, spinbox, minimum):
        """Robuste Seitenwahl mit eigenen, immer funktionierenden Pfeiltasten."""
        box=QHBoxLayout();box.setSpacing(0)
        spinbox.setMinimum(minimum);spinbox.setMinimumWidth(92)
        box.addWidget(spinbox)
        buttons=QVBoxLayout();buttons.setSpacing(0);buttons.setContentsMargins(2,0,0,0)
        up=QPushButton('▲');down=QPushButton('▼')
        for button in (up,down):
            button.setFixedSize(30,22);button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        up.clicked.connect(spinbox.stepUp)
        down.clicked.connect(spinbox.stepDown)
        buttons.addWidget(up);buttons.addWidget(down)
        box.addLayout(buttons)
        return box

    def books_page(self):
        w=QWidget();l=QVBoxLayout(w);l.addWidget(self.head('Bücher','Vorhandene Bücher auswählen, erneut erkennen und durchsuchen.'))
        self.book_table.cellDoubleClicked.connect(self.load_book_from_table);l.addWidget(self.book_table,1)
        r=QHBoxLayout()
        for text,fn in [('Buch in Suchmaske laden',self.load_selected_book),('Texterkennung erneut starten',self.rerun_htr),('Buch erneut durchsuchen',self.rerun_htr),('Buchordner öffnen',self.open_selected_book),('Aktualisieren',self.refresh)]:
            b=QPushButton(text);b.clicked.connect(fn);r.addWidget(b)
        r.addStretch();l.addLayout(r)
        self.bookinfo=QPlainTextEdit();self.bookinfo.setReadOnly(True);self.bookinfo.setMaximumHeight(140);l.addWidget(self.bookinfo)
        return w
    def hits_page(self):
        w=QWidget();l=QVBoxLayout(w);l.addWidget(self.head('Treffer prüfen','Echte Treffer bestätigen, falsche Treffer verwerfen und bei Bedarf wiederherstellen.'))
        review=QHBoxLayout()
        self.hit_filter=QComboBox();self.hit_filter.addItems(['Offene Treffer','Alle Treffer','Bestätigte Treffer','Verworfene Treffer']);self.hit_filter.currentIndexChanged.connect(self.apply_hit_filter)
        confirm=QPushButton('✓ Bestätigen');confirm.clicked.connect(lambda:self.rate_current_hit('confirmed'))
        reject=QPushButton('✗ Verwerfen');reject.clicked.connect(lambda:self.rate_current_hit('rejected'))
        restore=QPushButton('↺ Als offen markieren');restore.clicked.connect(lambda:self.rate_current_hit('open'))
        self.review_status=QLabel('Offen: 0   Bestätigt: 0   Verworfen: 0')
        review.addWidget(QLabel('Anzeige'));review.addWidget(self.hit_filter);review.addSpacing(12);review.addWidget(confirm);review.addWidget(reject);review.addWidget(restore);review.addStretch();review.addWidget(self.review_status);l.addLayout(review)
        r=QHBoxLayout();b=QPushButton('Treffer neu laden');b.clicked.connect(self.load_hits);h=QPushButton('Bericht öffnen');h.clicked.connect(self.open_report)
        for text,fn in [('Zoom +',self.scan_view.zoom_in),('Zoom −',self.scan_view.zoom_out),('Einpassen',self.scan_view.fit),('90° drehen',self.scan_view.rotate_right)]:q=QPushButton(text);q.clicked.connect(fn);r.addWidget(q)
        self.text_toggle=QPushButton('Text anzeigen');self.text_toggle.setCheckable(True);self.text_toggle.toggled.connect(self.toggle_ocr_panel)
        r.addWidget(b);r.addWidget(h);r.addWidget(self.text_toggle);r.addStretch();l.addLayout(r)
        sp=QSplitter();left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(0,0,0,0);ll.addWidget(self.table);right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(0,0,0,0);rl.addWidget(self.scan_title);self.position_status=QLabel('Position: –');rl.addWidget(self.position_status);self.content_split=QSplitter(Qt.Orientation.Horizontal);scan_panel=QWidget();scan_layout=QVBoxLayout(scan_panel);scan_layout.setContentsMargins(0,0,0,0);scan_layout.addWidget(self.scan_view,1);self.ocr_panel=QWidget();self.ocr_panel.setMinimumWidth(230);self.ocr_panel.setMaximumWidth(360);text_layout=QVBoxLayout(self.ocr_panel);text_layout.setContentsMargins(8,0,0,0);text_layout.addWidget(self.ocr_title);text_layout.addWidget(self.ocr_text,1);self.content_split.addWidget(scan_panel);self.content_split.addWidget(self.ocr_panel);self.content_split.setStretchFactor(0,6);self.content_split.setStretchFactor(1,1);self.ocr_panel.hide();rl.addWidget(self.content_split,1)
        navrow=QHBoxLayout();prev=QPushButton('◀ Vorherige Seite');prev.clicked.connect(self.previous_page);nxt=QPushButton('Nächste Seite ▶');nxt.clicked.connect(self.next_page);navrow.addWidget(prev);navrow.addStretch();navrow.addWidget(self.page_label);navrow.addStretch();navrow.addWidget(nxt);rl.addLayout(navrow)
        sp.addWidget(left);sp.addWidget(right);sp.setStretchFactor(0,3);sp.setStretchFactor(1,4);l.addWidget(sp,1)
        self.table.cellClicked.connect(self.preview_hit);self.table.cellDoubleClicked.connect(self.open_hit);return w
    def toggle_ocr_panel(self,visible):
        if not hasattr(self,'ocr_panel'):
            return
        self.ocr_panel.setVisible(bool(visible))
        if hasattr(self,'text_toggle'):
            self.text_toggle.setText('Text ausblenden' if visible else 'Text anzeigen')
        if visible and hasattr(self,'content_split'):
            total=max(800,self.content_split.width())
            self.content_split.setSizes([max(520,total-300),300])
        elif hasattr(self,'scan_view'):
            QTimer.singleShot(0,self.scan_view.fit)

    def statistics_page(self):
        w=QWidget();l=QVBoxLayout(w);l.addWidget(self.head('Statistik','Überblick über den lokalen Forschungsbestand.'));self.stattext=QPlainTextEdit();self.stattext.setReadOnly(True);l.addWidget(self.stattext);return w
    def settings_page(self):
        w=QWidget();l=QVBoxLayout(w);l.addWidget(self.head('Einstellungen','Lokaler ArchivAgent-Ordner.'));g=QGroupBox('Installation');f=QFormLayout(g);r=QHBoxLayout();r.addWidget(self.base);b=QPushButton('Auswählen');b.clicked.connect(self.choose_base);r.addWidget(b);f.addRow('ArchivAgent-Ordner',r);l.addWidget(g);l.addStretch();return w
    def task_panel(self):
        w=QWidget();l=QVBoxLayout(w);self.live_status=QLabel('Bereit');l.addWidget(self.live_status)
        self.archivist=ReadingArchivist();l.addWidget(self.archivist)
        l.addWidget(QLabel('Protokoll'));l.addWidget(self.log);l.addWidget(self.progress);return w
    def toolbar(self):
        t=QToolBar();self.addToolBar(t)
        for text,fn in [('Projekt öffnen',self.open_project),('Trefferbericht',self.open_report),('Aktualisieren',self.refresh)]:a=QAction(text,self);a.triggered.connect(fn);t.addAction(a)
    def bd(self):return Path(self.base.text().strip())
    def pd(self):return self.bd()/'Projekte'/safe_name(self.project.currentText())
    def bkd(self):return self.pd()/safe_name(self.book.currentText())
    def refresh(self):
        cur=self.project.currentText();d=self.bd()/'Projekte';names=sorted([p.name for p in d.iterdir() if p.is_dir()]) if d.exists() else [];self.project.blockSignals(True);self.project.clear();self.project.addItems(names);self.project.setCurrentText(cur);self.project.blockSignals(False);self.refresh_books();self.load_book_table();self.update_stats();self.load_hits()
    def refresh_books(self):
        cur=self.book.currentText();d=self.pd();names=sorted([p.name for p in d.iterdir() if p.is_dir() and p.name.casefold() not in {'treffer','berichte'}]) if d.exists() else [];self.book.clear();self.book.addItems(names);self.book.setCurrentText(cur);self.update_book()
    def update_book(self):
        if not hasattr(self,'bookinfo'):return
        if hasattr(self,'current_selection'):self.current_selection.setText(f'Aktuelle Auswahl: {self.project.currentText()}  →  {self.book.currentText()}')
        d=self.bkd();imgs=find_images(d) if d.exists() else [];s=f'Buchordner: {d}\nScans: {len(imgs)}\n';q=d/'quelle.txt';s+=('\n'+q.read_text(encoding='utf-8',errors='replace')) if q.exists() else '';self.bookinfo.setPlainText(s)
    def update_stats(self):
        d=self.bd()/'Projekte';ps=[p for p in d.iterdir() if p.is_dir()] if d.exists() else [];books=scans=0
        for p in ps:
            for b in p.iterdir():
                if b.is_dir() and b.name.casefold() not in {'treffer','berichte'}:books+=1;scans+=len(find_images(b))
        vals={'Projekte':len(ps),'Bücher':books,'Scans':scans,'Treffer':len(read_hits(self.pd())) if self.project.currentText() else 0}
        for k,v in vals.items():self.stats[k].setText(str(v))
        if hasattr(self,'stattext'):self.stattext.setPlainText('\n'.join(f'{k}: {v}' for k,v in vals.items()))
    def load_book_table(self):
        if not hasattr(self,'book_table'):return
        pd=self.pd();books=[b for b in pd.iterdir() if b.is_dir() and b.name.casefold() not in {'treffer','berichte'}] if pd.exists() else []
        all_hits=read_hits(pd);self.book_table.setRowCount(len(books))
        for r,b in enumerate(sorted(books,key=lambda x:x.name.casefold())):
            imgs=find_images(b);htr=any(b.rglob('*.txt'));count=sum(1 for h in all_hits if not h['book'] or safe_name(h['book']).casefold()==b.name.casefold())
            vals=[b.name,str(len(imgs)),'✓' if imgs else '—','✓' if htr else '—',str(count)]
            for c,v in enumerate(vals):self.book_table.setItem(r,c,QTableWidgetItem(v))
        self.book_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
    def selected_book_name(self):
        r=self.book_table.currentRow();i=self.book_table.item(r,0) if r>=0 else None;return i.text() if i else ''
    def load_selected_book(self):
        name=self.selected_book_name()
        if not name:return
        self.book.setCurrentText(name);q=self.pd()/name/'quelle.txt'
        if q.exists():
            m=re.search(r'DFG-Viewer:\s*\n([^\n]+)',q.read_text(encoding='utf-8',errors='replace'))
            if m:self.url.setText(m.group(1).strip())
        self.nav.setCurrentRow(0);self.update_book()
    def load_book_from_table(self,r,c):self.book_table.selectRow(r);self.load_selected_book()
    def rerun_htr(self):
        self.load_selected_book();self.force.setChecked(True);self.start_task('htr')
    def open_selected_book(self):
        name=self.selected_book_name()
        if name:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.pd()/name)))
    def ratings_path(self):
        d=self.pd()/'Treffer';d.mkdir(parents=True,exist_ok=True)
        return d/'Treffer_Bewertung.json'

    def hit_rating_key(self,h):
        parts=[h.get('book',''),h.get('page',''),h.get('name',''),h.get('line',''),Path(h.get('image','')).name,h.get('context','')]
        return '|'.join(str(x).strip().casefold() for x in parts)

    def load_ratings(self):
        try:
            p=self.ratings_path()
            data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
            self.hit_ratings=data if isinstance(data,dict) else {}
        except Exception:
            self.hit_ratings={}

    def save_ratings(self):
        p=self.ratings_path();tmp=p.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.hit_ratings,ensure_ascii=False,indent=2),encoding='utf-8')
        tmp.replace(p)

    def rating_for(self,h):
        return self.hit_ratings.get(self.hit_rating_key(h),'open')

    def rating_label(self,status):
        return {'confirmed':'✓ Bestätigt','rejected':'✗ Verworfen','open':'○ Offen'}.get(status,'○ Offen')

    def load_hits(self):
        self.all_hit_rows=read_hits(self.pd()) if self.project.currentText() else []
        self.load_ratings();self.apply_hit_filter()
        if hasattr(self,'log'):
            self.log.appendPlainText(f'[TREFFERIMPORT] {len(self.all_hit_rows)} Trefferzeile(n) geladen aus {self.pd()}')

    def apply_hit_filter(self,*_):
        mode=self.hit_filter.currentIndex() if hasattr(self,'hit_filter') else 0
        wanted={0:'open',2:'confirmed',3:'rejected'}.get(mode)
        self.hit_rows=[h for h in self.all_hit_rows if wanted is None or self.rating_for(h)==wanted]
        self.table.setRowCount(len(self.hit_rows))
        for r,h in enumerate(self.hit_rows):
            vals=[self.rating_label(self.rating_for(h)),h['name'],h['book'],h['page'],h['confidence'],h['context'],h['source']]
            for c,v in enumerate(vals):self.table.setItem(r,c,QTableWidgetItem(v))
        self.table.horizontalHeader().setSectionResizeMode(5,QHeaderView.ResizeMode.Stretch)
        counts={x:sum(1 for h in self.all_hit_rows if self.rating_for(h)==x) for x in ('open','confirmed','rejected')}
        if hasattr(self,'review_status'):self.review_status.setText(f"Offen: {counts['open']}   Bestätigt: {counts['confirmed']}   Verworfen: {counts['rejected']}")
        if self.hit_rows:
            self.table.selectRow(0);self.preview_hit(0)
        else:
            self.current_hit=None;self.scan_title.setText('Keine Treffer in dieser Auswahl.');self.position_status.setText('Position: –');self.ocr_text.clear();self.ocr_title.setText('Erkannter Text')

    def rate_current_hit(self,status):
        row=self.table.currentRow()
        if row<0 or row>=len(self.hit_rows):
            QMessageBox.information(self,'Treffer prüfen','Bitte zuerst einen Treffer auswählen.');return
        h=self.hit_rows[row];key=self.hit_rating_key(h);previous=self.hit_ratings.get(key,'open');self.last_rating_action=(key,previous);self.hit_ratings[key]=status
        try:self.save_ratings()
        except Exception as e:
            QMessageBox.critical(self,'Treffer prüfen',f'Die Bewertung konnte nicht gespeichert werden:\n{e}');return
        self.apply_hit_filter()
        if self.hit_rows:self.table.selectRow(min(row,len(self.hit_rows)-1));self.preview_hit(min(row,len(self.hit_rows)-1))
        self.statusBar().showMessage(self.rating_label(status),2500)

    def undo_last_rating(self):
        if not self.last_rating_action:
            self.statusBar().showMessage('Keine Bewertung zum Rückgängigmachen.',2500);return
        key,previous=self.last_rating_action
        if previous=='open':self.hit_ratings.pop(key,None)
        else:self.hit_ratings[key]=previous
        try:self.save_ratings()
        except Exception as e:
            QMessageBox.critical(self,'Treffer prüfen',f'Die Änderung konnte nicht gespeichert werden:\n{e}');return
        self.last_rating_action=None;self.apply_hit_filter();self.statusBar().showMessage('Letzte Bewertung rückgängig gemacht.',2500)

    def keyPressEvent(self,event):
        if self.stack.currentIndex()==2:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key()==Qt.Key.Key_Z:self.undo_last_rating();return
            if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.rate_current_hit('confirmed');return
            if event.key()==Qt.Key.Key_Delete:self.rate_current_hit('rejected');return
            if event.key()==Qt.Key.Key_Down:
                r=min(self.table.rowCount()-1,self.table.currentRow()+1);self.table.selectRow(r);self.preview_hit(r);return
            if event.key()==Qt.Key.Key_Up:
                r=max(0,self.table.currentRow()-1);self.table.selectRow(r);self.preview_hit(r);return
        super().keyPressEvent(event)

    def resolve_hit_image(self,h):
        candidates=[];book=safe_name(h.get('book') or self.book.currentText());bd=self.pd()/book
        raw=h.get('image','')
        if raw:
            rp=Path(raw);candidates += [rp,bd/rp,bd/'Originalseiten'/rp.name]
        page=h.get('page','');nums=re.findall(r'\d+',page)
        images=find_images(bd)
        if nums:
            n=int(nums[-1]);candidates += [x for x in images if re.search(rf'(?<!\d)0*{n}(?!\d)',x.stem)]
            if 1<=n<=len(images):candidates.append(images[n-1])
        candidates += images[:1]
        return next((x for x in candidates if x.exists()),None)
    def show_page_index(self,index):
        if not self.current_images:return
        index=max(0,min(index,len(self.current_images)-1));self.current_image_index=index
        img=self.current_images[index]
        if self.scan_view.show_image(img):
            self.scan_title.setText(img.name);self.page_label.setText(f'Seite {index+1} / {len(self.current_images)}')

    def previous_page(self):self.show_page_index(self.current_image_index-1)
    def next_page(self):self.show_page_index(self.current_image_index+1)

    def positions_path(self):
        d=self.pd()/'Treffer';d.mkdir(parents=True,exist_ok=True)
        return d/'Treffer_Korrekturen.json'

    def hit_position_key(self,h,img=None):
        image_name=(img.name if img else Path(h.get('image','')).name)
        parts=[h.get('book',''),h.get('page',''),h.get('name',''),h.get('line',''),image_name,h.get('textfile','')]
        return '|'.join(str(x).strip().casefold() for x in parts)

    def load_positions(self):
        p=self.positions_path()
        if not p.exists():return {}
        try:
            data=json.loads(p.read_text(encoding='utf-8'))
            return data if isinstance(data,dict) else {}
        except Exception:return {}

    def save_positions(self,data):
        p=self.positions_path();tmp=p.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        tmp.replace(p)

    def saved_bbox(self,h,img):
        key=self.hit_position_key(h,img);entry=self.load_positions().get(key)
        if not isinstance(entry,dict):return None
        try:return tuple(float(entry[k]) for k in ('x','y','w','h'))
        except Exception:return None

    def marker_moved(self):
        if hasattr(self,'position_status') and self.current_hit:
            self.position_status.setText('Position: geändert – Rechtsklick zum Speichern')

    def save_current_marker(self):
        if not self.current_hit or not self.current_position_key:return
        bbox=self.scan_view.marker_bbox()
        if not bbox:return
        data=self.load_positions();x,y,w,h=bbox
        data[self.current_position_key]={'x':round(x,2),'y':round(y,2),'w':round(w,2),'h':round(h,2),'book':self.current_hit.get('book',''),'page':self.current_hit.get('page',''),'name':self.current_hit.get('name','')}
        self.save_positions(data)
        self.position_status.setText('Position: manuell gespeichert')
        self.statusBar().showMessage('Trefferposition gespeichert.',3000)

    def reset_current_marker(self):
        if not self.current_hit or not self.current_position_key:return
        data=self.load_positions()
        if self.current_position_key in data:
            del data[self.current_position_key];self.save_positions(data)
        if self.current_auto_bbox and self.scan_view.rect:
            x,y,w,h=self.current_auto_bbox;self.scan_view.rect.setRect(QRectF(0,0,w,h));self.scan_view.rect.setPos(x,y);self.scan_view.centerOn(self.scan_view.rect.sceneBoundingRect().center())
        self.position_status.setText('Position: automatisch')
        self.statusBar().showMessage('Automatische Position wiederhergestellt.',3000)

    def estimated_line_bbox(self,h,img):
        # Exakte Koordinaten haben immer Vorrang, sobald Backend/CSV sie liefert.
        try:
            if all(h.get(k) for k in ('x','y','w','h')):
                return tuple(float(str(h[k]).replace(',','.')) for k in ('x','y','w','h')), 'exakt'
        except Exception:
            pass
        try:
            line_no=int(float(str(h.get('line','')).replace(',','.')))
        except Exception:
            return None, ''
        if line_no < 1:return None, ''
        pm=QPixmap(str(img))
        if pm.isNull():return None, ''
        total_lines=0
        raw=h.get('textfile','')
        candidates=[]
        if raw:
            rp=Path(raw);book=safe_name(h.get('book') or self.book.currentText());bd=self.pd()/book
            candidates += [rp,bd/rp,bd/'HTR'/rp.name,bd/'OCR'/rp.name,bd/'Texte'/rp.name]
        # Fallback: gleiche Basis wie Bilddatei suchen.
        for folder in [img.parent,img.parent.parent,img.parent.parent/'HTR',img.parent.parent/'OCR',img.parent.parent/'Texte']:
            candidates += [folder/(img.stem+'.txt')]
        txt=next((x for x in candidates if x.exists() and x.is_file()),None)
        if txt:
            try:
                lines=txt.read_text(encoding='utf-8-sig',errors='replace').splitlines()
                total_lines=max(len([x for x in lines if x.strip()]),len(lines))
            except Exception:
                total_lines=0
        # Ohne lesbare Textdatei ist 40 eine konservative typische Zeilenzahl.
        total_lines=max(total_lines,line_no,40 if not total_lines else total_lines)
        iw,ih=pm.width(),pm.height()
        band=max(24.0,ih/total_lines*1.45)
        # Die Trefferzeilennummer liegt bei den aktuellen TXT-Dateien optisch
        # Nach der ersten Korrektur lag die Markierung zwischen zwei Zeilen.
        # Daher nochmals eine halbe geschätzte Zeilenhöhe nach unten verschieben.
        center=(min(total_lines+0.5,line_no+1.5)-.5)/total_lines*ih
        y=max(0.0,min(ih-band,center-band/2))
        return (iw*.025,y,iw*.95,band),'geschätzt'

    def resolve_hit_textfile(self,h,img=None):
        """Findet die zur Bildseite gehörende TXT-Datei robust in älteren und neuen Projektstrukturen."""
        candidates=[]
        book=safe_name(h.get('book') or self.book.currentText());bd=self.pd()/book
        raw=h.get('textfile','')
        if raw:
            rp=Path(raw)
            candidates += [rp,bd/rp,bd/'HTR'/rp.name,bd/'HTR'/'Texte'/rp.name,bd/'OCR'/rp.name,bd/'OCR'/'Texte'/rp.name,bd/'Texte'/rp.name]
        if img:
            stem=img.stem+'.txt'
            candidates += [img.with_suffix('.txt'),bd/'HTR'/stem,bd/'HTR'/'Texte'/stem,bd/'OCR'/stem,bd/'OCR'/'Texte'/stem,bd/'Texte'/stem]
        seen=set()
        for candidate in candidates:
            try:
                key=str(candidate.resolve())
            except Exception:
                key=str(candidate)
            if key in seen:continue
            seen.add(key)
            if candidate.exists() and candidate.is_file():return candidate
        if img:
            matches=list(bd.rglob(img.stem+'.txt'))
            if matches:return matches[0]
        return None

    def show_hit_text(self,h,img=None):
        self.ocr_text.clear();self.ocr_title.setText('Erkannter Text')
        txt=self.resolve_hit_textfile(h,img)
        if not txt:
            self.ocr_text.setPlainText('Für diesen Treffer wurde keine passende Textdatei gefunden.\n\nDie Originalseite kann trotzdem geprüft werden.')
            return
        try:
            content=txt.read_text(encoding='utf-8-sig',errors='replace')
        except Exception as exc:
            self.ocr_text.setPlainText(f'Die Textdatei konnte nicht gelesen werden:\n{exc}')
            return
        self.ocr_title.setText(f'Erkannter Text — {txt.name}')
        self.ocr_text.setPlainText(content)
        document=self.ocr_text.document()
        formats=[]
        # Zuerst das tatsächlich erkannte Trefferwort, danach mögliche Suchvarianten.
        terms=[]
        for value in (h.get('name',''),):
            value=str(value).strip()
            if value and value.casefold() not in {x.casefold() for x in terms}:terms.append(value)
        context=str(h.get('context','')).strip()
        if context and len(context)<100:
            for word in re.findall(r"[A-Za-zÄÖÜäöüßſ]+",context):
                if len(word)>=5 and word.casefold() not in {x.casefold() for x in terms}:terms.append(word)
        first_cursor=None
        for index,term in enumerate(terms[:5]):
            cursor=QTextCursor(document)
            fmt=QTextCharFormat();fmt.setBackground(QColor('#ffd54f' if index==0 else '#fff3b0'));fmt.setForeground(QColor('#111111'))
            while True:
                cursor=document.find(term,cursor,QTextDocument.FindFlag(0))
                if cursor.isNull():break
                extra=QTextEdit.ExtraSelection();extra.cursor=cursor;extra.format=fmt;formats.append(extra)
                if first_cursor is None:first_cursor=QTextCursor(cursor)
        # Fallback: Zeilennummer aus der Trefferliste anspringen und Zeile markieren.
        if first_cursor is None:
            try:line_no=int(float(str(h.get('line','')).replace(',','.')))
            except Exception:line_no=0
            if line_no>0:
                block=document.findBlockByNumber(line_no-1)
                if block.isValid():
                    cursor=QTextCursor(block);cursor.select(QTextCursor.SelectionType.LineUnderCursor)
                    fmt=QTextCharFormat();fmt.setBackground(QColor('#fff3b0'))
                    extra=QTextEdit.ExtraSelection();extra.cursor=cursor;extra.format=fmt;formats.append(extra);first_cursor=QTextCursor(cursor)
        self.ocr_text.setExtraSelections(formats)
        if first_cursor:
            self.ocr_text.setTextCursor(first_cursor);self.ocr_text.ensureCursorVisible()

    def preview_hit(self,r,c=0):
        if r<0 or r>=len(self.hit_rows):return
        h=self.hit_rows[r];img=self.resolve_hit_image(h);bbox=None;quality='';self.current_hit=h;self.current_position_key=self.hit_position_key(h,img) if img else None;self.show_hit_text(h,img)
        if img:
            self.current_auto_bbox,quality=self.estimated_line_bbox(h,img)
            saved=self.saved_bbox(h,img)
            if saved:bbox=saved;quality='manuell gespeichert'
            else:bbox=self.current_auto_bbox
        if img:
            self.current_images=find_images(img.parent.parent if img.parent.name.casefold() in {'originalseiten','scans'} else img.parent)
            try:self.current_image_index=self.current_images.index(img)
            except ValueError:self.current_image_index=-1
            self.page_label.setText(f'Seite {self.current_image_index+1} / {len(self.current_images)}' if self.current_image_index>=0 else 'Seite – / –')
        if img and self.scan_view.show_image(img,bbox):
            marker=f' — Zeile {h.get("line","?")} markiert ({quality})' if bbox else ''
            self.scan_title.setText(f"{h['name']} — {h['book']} — Seite {h['page']}"+marker)
            self.position_status.setText('Position: manuell gespeichert' if quality=='manuell gespeichert' else 'Position: automatisch')
        else:self.scan_title.setText('Die Originalseite konnte nicht automatisch zugeordnet werden.');self.position_status.setText('Position: –')
    def start_task(self,a):
        if self.thread and self.thread.isRunning():QMessageBox.information(self,'ArchivAgent','Es läuft bereits ein Vorgang.');return
        start_page=self.start.value(); end_page=self.end.value()
        if end_page and end_page < start_page:
            QMessageBox.warning(self,'Seitenbereich prüfen','Die Endseite darf nicht kleiner als die Startseite sein.');return
        page_limit=0 if end_page==0 else end_page-start_page+1
        p={'base':str(self.bd()),'project':self.project.currentText().strip(),'book':self.book.currentText().strip(),'url':self.url.text().strip(),'start':start_page,'end':end_page,'limit':page_limit,'threshold':self.threshold.value(),'force':self.force.isChecked(),'names':self.names.text().strip()}
        if not p['project'] or not p['book']:QMessageBox.warning(self,'Eingabe prüfen','Projekt und Buch ausfüllen.');return
        local_mode_count=0
        if a in ('download','all') and not p['url']:
            local_images=find_images(self.bkd())
            if a=='all' and local_images:
                a='htr'
                local_mode_count=len(local_images)
            else:
                QMessageBox.warning(
                    self,'Eingabe prüfen',
                    'Für den Download fehlt ein METS-/DFG-Viewer-Link.\n\n'
                    'Eigene Scans bitte zuerst über „Eigene Scans/Bilder hinzufügen“ importieren.'
                );return
        self.log.appendPlainText('\n'+'='*60);self.log.appendPlainText(f"[BEREICH] Suche Seiten {p['start']} bis {p['end'] if p['end'] else 'Ende'} ({p['limit'] if p['limit'] else 'alle restlichen'} Seite(n))")
        if local_mode_count:self.log.appendPlainText(f'[MODUS] Kein Viewer-Link angegeben; {local_mode_count} eigene Bilddatei(en) werden direkt erkannt und durchsucht.')
        self.archivist.stop();self.live_status.setText('Vorgang wird vorbereitet');self.progress.setRange(0,0);self.thread=QThread(self);self.worker=Worker(a,p);self.worker.moveToThread(self.thread);self.thread.started.connect(self.worker.run);self.worker.log.connect(self.log.appendPlainText);self.worker.progress.connect(self.update_progress);self.worker.stage.connect(self.update_stage);self.worker.finished.connect(self.worker_done);self.thread.finished.connect(self.thread_done);self.thread.start()
    @Slot(str)
    def update_stage(self,text):
        self.live_status.setText(text)
        if text.startswith('Texterkennung'):self.archivist.start()
    @Slot(int, int)
    def update_progress(self, current, total):
        # Wird garantiert im GUI-Hauptthread ausgeführt.
        total = max(int(total), 1)
        current = max(0, min(int(current), total))
        self.progress.setRange(0, total)
        self.progress.setValue(current)

    def worker_done(self,ok,msg):
        self.pending_result=(bool(ok),str(msg))
        if self.thread:self.thread.quit()
    def thread_done(self):
        try:
            ok,msg=self.pending_result or (False,'Der Vorgang wurde unerwartet beendet.')
            self.pending_result=None
            self.live_status.setText('Abgeschlossen – Treffer geladen' if ok else 'Vorgang beendet')
            if ok:self.archivist.finish()
            else:self.archivist.stop()
            self.progress.setRange(0,100);self.progress.setValue(100 if ok else 0)
            # Trefferdateien werden ausschließlich nach Ende der Texterkennung eingelesen.
            QTimer.singleShot(100,self.safe_finish_refresh)
            (QMessageBox.information if ok else QMessageBox.critical)(self,'ArchivAgent',msg)
        except Exception as e:
            write_crash_log('Fehler in thread_done',e)
            QMessageBox.critical(self,'ArchivAgent',f'Abschlussfehler: {e}\n\nDetails stehen in archivagent_crash.log.')
    def safe_finish_refresh(self):
        try:self.refresh()
        except Exception as e:
            self.log.appendPlainText(f'[ABSCHLUSS-FEHLER] {e}')
            write_crash_log('Fehler beim Abschluss-Refresh',e)
    def cancel(self):
        if self.worker:self.worker.cancel()
    def open_project(self):d=self.pd();d.mkdir(parents=True,exist_ok=True);QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))
    def open_book(self):d=self.bkd();d.mkdir(parents=True,exist_ok=True);QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))
    def open_report(self):
        hs=sorted(list(self.pd().rglob('*.html')),key=lambda p:p.stat().st_mtime,reverse=True) if self.pd().exists() else []
        if hs:QDesktopServices.openUrl(QUrl.fromLocalFile(str(hs[0])))
        else:QMessageBox.information(self,'ArchivAgent','Noch kein HTML-Bericht vorhanden.')
    def open_hit(self,r,c):
        self.preview_hit(r,c)
        if 0<=r<len(self.hit_rows):
            img=self.resolve_hit_image(self.hit_rows[r])
            if img:QDesktopServices.openUrl(QUrl.fromLocalFile(str(img)))
    def choose_base(self):
        d=QFileDialog.getExistingDirectory(self,'ArchivAgent-Ordner',self.base.text())
        if d:self.base.setText(d);self.refresh()
    def import_own_images(self):
        project=self.project.currentText().strip();book=self.book.currentText().strip()
        if not project or not book:
            QMessageBox.warning(self,'Eigene Bilder hinzufügen','Bitte zuerst Projekt und Buch angeben.');return
        files,_=QFileDialog.getOpenFileNames(
            self,'Eigene Scans oder Bilder auswählen','',
            'Bilddateien (*.png *.jpg *.jpeg *.tif *.tiff *.jp2 *.webp);;Alle Dateien (*)'
        )
        if not files:return
        try:
            imported=import_image_files(files,self.bkd())
            if not imported:
                QMessageBox.warning(self,'Eigene Bilder hinzufügen','Keine unterstützten Bilddateien ausgewählt.');return
            first=image_page_number(imported[0]) or 1;last=image_page_number(imported[-1]) or first
            self.start.setValue(first);self.end.setValue(last);self.url.clear();self.refresh()
            self.project.setCurrentText(project);self.refresh_books();self.book.setCurrentText(book);self.update_book()
            QMessageBox.information(
                self,'Bilder hinzugefügt',
                f'{len(imported)} Bilddatei(en) wurden in Originalseiten eingefügt und als '
                f'Seite {first} bis {last} nummeriert.\n\n'
                'Familiennamen eintragen und anschließend „Alles automatisch starten“ wählen.'
            )
        except Exception as exc:
            write_crash_log('Fehler beim Import eigener Bilder',exc)
            QMessageBox.critical(self,'Import fehlgeschlagen',str(exc))
    def style(self):self.setStyleSheet("QMainWindow,QWidget{background:#f4f6f8;color:#1f2933;font-family:'Segoe UI';font-size:10.5pt} QListWidget{background:#17212b;color:#e7edf3;border:0;padding:10px;font-size:11pt} QListWidget::item{padding:13px 12px;border-radius:6px} QListWidget::item:selected{background:#2d80c3;color:white} QGroupBox,QFrame#card{background:white;border:1px solid #d8dee5;border-radius:8px;margin-top:10px;padding:14px} QLineEdit,QSpinBox,QDoubleSpinBox,QPlainTextEdit,QComboBox,QTableWidget{background:white;border:1px solid #c8d0d9;border-radius:5px;padding:6px} QPushButton{background:white;border:1px solid #aeb8c2;border-radius:6px;padding:8px 14px} QPushButton#primary{background:#1769aa;color:white;border:1px solid #1769aa;font-weight:600} QProgressBar{border:1px solid #c8d0d9;border-radius:5px;background:white;text-align:center} QProgressBar::chunk{background:#2d80c3}")

def crash_log_path():
    try:return Path(BASE_DEFAULT)/'archivagent_crash.log'
    except Exception:return Path.cwd()/'archivagent_crash.log'

def write_crash_log(title,exc=None):
    try:
        p=crash_log_path();p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('a',encoding='utf-8') as f:
            f.write('\n'+'='*70+'\n'+title+'\n')
            if exc is not None:
                f.write(''.join(traceback.format_exception(type(exc),exc,exc.__traceback__)))
            else:
                f.write(''.join(traceback.format_stack()))
    except Exception:
        pass

def main():
    crash_file=None
    try:
        cp=crash_log_path();cp.parent.mkdir(parents=True,exist_ok=True)
        crash_file=cp.open('a',encoding='utf-8')
        faulthandler.enable(crash_file,all_threads=True)
    except Exception:
        crash_file=None
    app=QApplication(sys.argv)
    def excepthook(exc_type,exc,tb):
        write_crash_log('Unbehandelte Ausnahme',exc)
        try:QMessageBox.critical(None,'ArchivAgent – Fehler',f'{exc}\n\nDetails: {crash_log_path()}')
        except Exception:pass
    sys.excepthook=excepthook
    w=Main();w.show();code=app.exec()
    if crash_file:crash_file.close()
    return code
if __name__=='__main__':raise SystemExit(main())
