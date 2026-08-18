from __future__ import annotations
import csv, json, os, re, ssl, subprocess, sys, traceback, faulthandler, urllib.parse, urllib.request, xml.etree.ElementTree as ET, copy
import certifi
from pathlib import Path
from archivagent.image_import import import_image_files
from archivagent.table_structure import detect_table_structure, draw_structure_overlay, load_structure, rebuild_cells, save_structure, scale_structure, transcription_from_grid, transcription_html_from_grid
from PySide6.QtCore import Qt, QThread, QUrl, QObject, Signal, Slot, QRectF, QTimer, QPointF, QProcess
from PySide6.QtGui import QAction, QDesktopServices, QFont, QPixmap, QPen, QColor, QTextCursor, QTextCharFormat, QTextDocument, QPainter, QBrush, QPolygonF, QPainterPathStroker, QTextTable
from PySide6.QtWidgets import (QApplication,QCheckBox,QComboBox,QDialog,QDoubleSpinBox,QFileDialog,QFormLayout,QFrame,QGridLayout,QGroupBox,QHBoxLayout,QLabel,QLineEdit,QListWidget,QMainWindow,QMessageBox,QPlainTextEdit,QTextEdit,QProgressBar,QPushButton,QSpinBox,QSplitter,QStackedWidget,QTableWidget,QTableWidgetItem,QToolBar,QVBoxLayout,QWidget,QGraphicsView,QGraphicsScene,QGraphicsPixmapItem,QGraphicsRectItem,QGraphicsLineItem,QGraphicsItem,QHeaderView,QMenu,QAbstractSpinBox,QScrollArea,QProgressDialog,QInputDialog)

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
            if not self.cancelled and self.action in ('htr','all','read'):self.htr()
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
        if self.p.get('read_only') and '--read-only' in help_text:cmd.append('--read-only')
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
        self.scene_click_callback=None
        self.min_zoom=0.5;self.max_zoom=8.0;self.overview_zoom=0.5

    def show_structure(self,structure):
        if not structure or not self.pix:return
        pen_h=QPen(QColor(230,45,45,205));pen_h.setWidth(4)
        pen_v=QPen(QColor(20,110,230,205));pen_v.setWidth(4)
        for y in structure.horizontal_lines:
            start,end=(structure.horizontal_extents or {}).get(str(y),[0,structure.image_width]);item=self.scene.addLine(start,y,end,y,pen_h);item.setZValue(8)
        for x in structure.vertical_lines:
            start,end=(structure.vertical_extents or {}).get(str(x),[0,structure.image_height]);item=self.scene.addLine(x,start,x,end,pen_v);item.setZValue(8)
        self.scene.update();self.viewport().update()

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
        if event.button()==Qt.MouseButton.LeftButton and self.scene_click_callback:
            point=self.mapToScene(event.position().toPoint())
            self.scene_click_callback(point.x(),point.y())
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

class StructuredTextEdit(QTextEdit):
    """Zeigt das gespeicherte Seitenraster auch über der Transkription."""
    def __init__(self,parent=None):
        super().__init__(parent);self.structure=None
        self.verticalScrollBar().valueChanged.connect(lambda _value:self.viewport().update())
        self.horizontalScrollBar().valueChanged.connect(lambda _value:self.viewport().update())
    def set_structure(self,structure):self.structure=structure;self.viewport().update()
    def paintEvent(self,event):
        super().paintEvent(event)
        if not self.structure:return
        painter=QPainter(self.viewport());painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        vw=max(1,self.viewport().width());vh=max(1,self.viewport().height())
        doc_height=max(float(self.document().documentLayout().documentSize().height()),float(vh))
        y_scroll=self.verticalScrollBar().value();x_scroll=self.horizontalScrollBar().value()
        painter.setPen(QPen(QColor(230,45,45,155),2))
        for y in self.structure.horizontal_lines:
            py=(y/max(1,self.structure.image_height))*doc_height-y_scroll
            if -2<=py<=vh+2:painter.drawLine(0,round(py),vw,round(py))
        painter.setPen(QPen(QColor(20,110,230,145),2))
        content_width=max(float(self.document().idealWidth()),float(vw))
        for x in self.structure.vertical_lines:
            px=(x/max(1,self.structure.image_width))*content_width-x_scroll
            if -2<=px<=vw+2:painter.drawLine(round(px),0,round(px),vh)

class FullPageReader(QDialog):
    """Gemeinsamer Vollbild-Lesemodus für Trefferseiten und eigene Scans."""
    def __init__(self,image_path,text_path=None,highlight='',bbox=None,structure_path=None,alto_path=None,parent=None,can_previous=False,can_next=False):
        super().__init__(parent)
        self.image_path=Path(image_path);self.raw_text_path=Path(text_path) if text_path else None
        self.alto_path=Path(alto_path) if alto_path else None;self.structure_path=Path(structure_path) if structure_path else None;self.corrected_path=self._corrected_path();self.name_highlight=str(highlight or '');self.suspicious_visible=False;self.structure=self._load_structure(structure_path);self.navigation_delta=0
        self.setWindowTitle(f'Ganze Seite lesen — {self.image_path.name}')
        self.resize(1180,900);self.setMinimumSize(820,640)
        layout=QVBoxLayout(self)
        tools=QHBoxLayout()
        for label,fn in [('Zoom +',lambda:self.image_view.zoom_in()),('Zoom −',lambda:self.image_view.zoom_out()),('Einpassen',lambda:self.image_view.fit()),('90° drehen',lambda:self.image_view.rotate_right())]:
            button=QPushButton(label);button.clicked.connect(fn);tools.addWidget(button)
        tools.addSpacing(12);tools.addWidget(QLabel('Markierten Text'))
        smaller=QPushButton('−');smaller.clicked.connect(lambda:self.change_text_size(-1));tools.addWidget(smaller)
        larger=QPushButton('+');larger.clicked.connect(lambda:self.change_text_size(1));tools.addWidget(larger)
        if self.structure_path:
            raster=QPushButton('Rasterlinien bearbeiten/löschen');raster.clicked.connect(self.edit_raster);tools.addWidget(raster)
        tools.addStretch()
        fullscreen=QPushButton('Vollbild');fullscreen.setCheckable(True);fullscreen.toggled.connect(self.toggle_fullscreen);tools.addWidget(fullscreen)
        layout.addLayout(tools)
        split=QSplitter(Qt.Orientation.Vertical)
        image_panel=QWidget();image_layout=QVBoxLayout(image_panel);image_layout.setContentsMargins(0,0,0,0)
        image_title=QLabel('Original');image_title.setFont(QFont('Segoe UI',11,QFont.Weight.Bold));image_layout.addWidget(image_title)
        self.image_view=ScanView();self.image_view.show_image(self.image_path,bbox);self.image_view.show_structure(self.structure);self.image_view.scene_click_callback=self.select_original_cell;image_layout.addWidget(self.image_view,1)
        text_panel=QWidget();text_layout=QVBoxLayout(text_panel);text_layout.setContentsMargins(0,8,0,0)
        text_title=QLabel('Transkription — Zeilen und Spalten nach dem Original angeordnet');text_title.setFont(QFont('Segoe UI',11,QFont.Weight.Bold));text_layout.addWidget(text_title)
        self.transcription=StructuredTextEdit();self.transcription_point_size=10;self.transcription.setAcceptRichText(True);self.transcription.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth);self.transcription.set_structure(None)
        self.transcription.setPlaceholderText('Für dieses Dokument liegt noch keine Transkription vor.')
        text_layout.addWidget(self.transcription,1)
        actions=QHBoxLayout()
        previous=QPushButton('◀ Vorherige Seite');previous.setEnabled(can_previous);previous.clicked.connect(lambda:self.navigate(-1));actions.addWidget(previous)
        following=QPushButton('Nächste Seite ▶');following.setEnabled(can_next);following.clicked.connect(lambda:self.navigate(1));actions.addWidget(following)
        actions.addSpacing(12)
        copy_button=QPushButton('Text kopieren');copy_button.clicked.connect(self.copy_text);actions.addWidget(copy_button)
        suspicious=QPushButton('Verdächtige Zeichen markieren');suspicious.setCheckable(True);suspicious.toggled.connect(self.highlight_suspicious);actions.addWidget(suspicious)
        save_button=QPushButton('Korrektur speichern');save_button.setObjectName('primary');save_button.clicked.connect(self.save_correction);actions.addWidget(save_button)
        export_button=QPushButton('Als TXT speichern');export_button.clicked.connect(self.export_text);actions.addWidget(export_button)
        actions.addStretch();close_button=QPushButton('Schließen');close_button.clicked.connect(self.accept);actions.addWidget(close_button);text_layout.addLayout(actions)
        split.addWidget(image_panel);split.addWidget(text_panel);split.setStretchFactor(0,3);split.setStretchFactor(1,2);split.setSizes([540,320]);layout.addWidget(split,1)
        self.load_text(highlight)
        if bbox and self.structure:QTimer.singleShot(0,lambda:self.select_hit_cell(highlight,bbox))
        QTimer.singleShot(0,self.image_view.fit)

    def navigate(self,delta):
        self.navigation_delta=int(delta);self.accept()

    def change_text_size(self,steps):
        cursor=self.transcription.textCursor()
        if not cursor.hasSelection():cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        if not cursor.hasSelection():
            QMessageBox.information(self,'Textgröße','Bitte zuerst ein Wort oder einen Textabschnitt markieren.');return
        current=cursor.charFormat().fontPointSize() or self.transcription.font().pointSizeF() or 10
        fmt=QTextCharFormat();fmt.setFontPointSize(max(6,min(28,current+int(steps))));cursor.mergeCharFormat(fmt)
        self.transcription.setTextCursor(cursor)

    def edit_raster(self):
        old_structure=copy.deepcopy(self.structure)
        old_cells=self.table_cell_texts()
        dialog=TableStructureDialog(self.image_path,None,self.structure,self.structure_path,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.structure=load_structure(self.structure_path);self.image_view.show_image(self.image_path);self.image_view.show_structure(self.structure);self.image_view.scene_click_callback=self.select_original_cell
            self.rebuild_transcription_preserving_corrections(old_structure,old_cells)
            QMessageBox.information(self,'Raster übernommen','Die geänderten Linien wurden gespeichert und direkt auf die Transkription angewendet. Vorhandene Korrekturen wurden positionsbezogen übernommen.')

    def table_cell_texts(self):
        table=next((frame for frame in self.transcription.document().rootFrame().childFrames() if isinstance(frame,QTextTable)),None)
        if table is None:return []
        result=[]
        for row in range(table.rows()):
            current=[]
            for column in range(table.columns()):
                cell=table.cellAt(row,column);cursor=cell.firstCursorPosition();cursor.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
                current.append(cursor.selectedText().replace('\u2029','\n').strip())
            result.append(current)
        return result

    def rebuild_transcription_preserving_corrections(self,old_structure,old_cells):
        if self.alto_path and self.alto_path.exists():self.transcription.setHtml(transcription_html_from_grid(self.alto_path,self.structure))
        table=next((frame for frame in self.transcription.document().rootFrame().childFrames() if isinstance(frame,QTextTable)),None)
        if table is None or not old_structure:return
        mapped={}
        for old_row,row_values in enumerate(old_cells):
            if old_row>=len(old_structure.horizontal_lines)-1:continue
            cy=sum(old_structure.horizontal_lines[old_row:old_row+2])/2
            new_row=next((i for i,(a,b) in enumerate(zip(self.structure.horizontal_lines,self.structure.horizontal_lines[1:])) if a<=cy<b),None)
            if new_row is None or new_row>=table.rows():continue
            for old_column,value in enumerate(row_values):
                if not value or old_column>=len(old_structure.vertical_lines)-1:continue
                cx=sum(old_structure.vertical_lines[old_column:old_column+2])/2
                new_column=next((i for i,(a,b) in enumerate(zip(self.structure.vertical_lines,self.structure.vertical_lines[1:])) if a<=cx<b),None)
                if new_column is None or new_column>=table.columns():continue
                mapped.setdefault((new_row,new_column),[]).append(value)
        for (new_row,new_column),values in mapped.items():
            cell=table.cellAt(new_row,new_column);cursor=cell.firstCursorPosition();cursor.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor);cursor.insertText('\n'.join(values))
        self.save_correction(silent=True)

    def _load_structure(self,path):
        if not path:return None
        try:
            data=json.loads(Path(path).read_text(encoding='utf-8'))
            from archivagent.table_structure import TableStructure
            return rebuild_cells(TableStructure(**data))
        except Exception:return None

    def _corrected_path(self):
        if not self.raw_text_path:return None
        folder=self.raw_text_path.parent.parent/'Korrekturen' if self.raw_text_path.parent.name.casefold() in {'texte','layout'} else self.raw_text_path.parent/'Korrekturen'
        return folder/self.raw_text_path.name

    def _corrected_html_path(self):
        return self.corrected_path.with_suffix('.html') if self.corrected_path else None

    def _training_pair_path(self):
        return self.corrected_path.with_suffix('.training.json') if self.corrected_path else None

    def _training_alto_path(self):
        return self.corrected_path.with_suffix('.groundtruth.xml') if self.corrected_path else None

    def save_training_alto(self):
        """Schreibt echte zeilenbezogene Ground-Truth im von Kraken lesbaren ALTO-Format."""
        if not self.structure or not self._training_alto_path():return None
        table=next((frame for frame in self.transcription.document().rootFrame().childFrames() if isinstance(frame,QTextTable)),None)
        if table is None:return None
        root=ET.Element('alto',{'xmlns':'http://www.loc.gov/standards/alto/ns-v4#'})
        description=ET.SubElement(root,'Description');ET.SubElement(description,'MeasurementUnit').text='pixel'
        source=ET.SubElement(description,'sourceImageInformation');ET.SubElement(source,'fileName').text=str(self.image_path.resolve())
        layout=ET.SubElement(root,'Layout');page=ET.SubElement(layout,'Page',{'WIDTH':str(self.structure.image_width),'HEIGHT':str(self.structure.image_height)})
        space=ET.SubElement(page,'PrintSpace',{'HPOS':'0','VPOS':'0','WIDTH':str(self.structure.image_width),'HEIGHT':str(self.structure.image_height)})
        block=ET.SubElement(space,'TextBlock',{'ID':'corrected_table'})
        line_id=0
        for row in range(min(table.rows(),len(self.structure.horizontal_lines)-1)):
            top,bottom=self.structure.horizontal_lines[row:row+2]
            for column in range(min(table.columns(),len(self.structure.vertical_lines)-1)):
                left,right=self.structure.vertical_lines[column:column+2];cell=table.cellAt(row,column)
                cursor=cell.firstCursorPosition();cursor.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
                values=[value.strip() for value in cursor.selectedText().replace('\u2029','\n').splitlines() if value.strip()]
                if not values:continue
                line_height=max(1,(bottom-top)//len(values))
                for index,value in enumerate(values):
                    y=top+index*line_height;line_id+=1
                    line=ET.SubElement(block,'TextLine',{'ID':f'line_{line_id}','HPOS':str(left),'VPOS':str(y),'WIDTH':str(max(1,right-left)),'HEIGHT':str(line_height)})
                    ET.SubElement(line,'String',{'ID':f'string_{line_id}','CONTENT':value,'HPOS':str(left),'VPOS':str(y),'WIDTH':str(max(1,right-left)),'HEIGHT':str(line_height)})
        if not line_id:return None
        path=self._training_alto_path();ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True);return path

    def load_text(self,highlight=''):
        corrected_html=self._corrected_html_path()
        source=self.corrected_path if self.corrected_path and self.corrected_path.exists() else self.raw_text_path
        if corrected_html and corrected_html.exists():
            self.transcription.setHtml(corrected_html.read_text(encoding='utf-8'))
        elif (not self.corrected_path or not self.corrected_path.exists()) and self.structure and self.alto_path and self.alto_path.exists():
            try:self.transcription.setHtml(transcription_html_from_grid(self.alto_path,self.structure))
            except Exception:
                if source and source.exists():self.transcription.setPlainText(source.read_text(encoding='utf-8-sig',errors='replace'))
        elif source and source.exists():
            self.transcription.setPlainText(source.read_text(encoding='utf-8-sig',errors='replace'))
        if highlight:
            cursor=self.transcription.document().find(str(highlight))
            if not cursor.isNull():
                fmt=QTextCharFormat();fmt.setBackground(QColor('#ffd54f'));fmt.setForeground(QColor('#111111'))
                extra=QTextEdit.ExtraSelection();extra.cursor=cursor;extra.format=fmt;self.transcription.setExtraSelections([extra]);self.transcription.setTextCursor(cursor);self.transcription.ensureCursorVisible()

    def select_original_cell(self,x,y):
        """Markiert nach einem Klick ins Original die zugehörige Rasterzelle im Text."""
        if not self.structure:return
        vertical=self.structure.vertical_lines;horizontal=self.structure.horizontal_lines
        row=next((i for i,(top,bottom) in enumerate(zip(horizontal,horizontal[1:])) if top<=y<bottom),None)
        column=next((i for i,(left,right) in enumerate(zip(vertical,vertical[1:])) if left<=x<right),None)
        if row is None or column is None:return
        table=next((frame for frame in self.transcription.document().rootFrame().childFrames() if isinstance(frame,QTextTable)),None)
        if table is None or row>=table.rows() or column>=table.columns():return
        cell=table.cellAt(row,column);cursor=cell.firstCursorPosition();cursor.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
        fmt=QTextCharFormat();fmt.setBackground(QColor('#80deea'));fmt.setForeground(QColor('#111111'))
        extra=QTextEdit.ExtraSelection();extra.cursor=cursor;extra.format=fmt
        self.transcription.setExtraSelections([extra]);self.transcription.setTextCursor(cursor);self.transcription.ensureCursorVisible()

    def select_hit_cell(self,name,bbox):
        """Sucht den Treffer nur in der durch die Bildmarkierung bestimmten Tabellenzeile."""
        if not self.structure:return
        _x,y,_w,h=bbox;center_y=y+h/2
        row=next((i for i,(top,bottom) in enumerate(zip(self.structure.horizontal_lines,self.structure.horizontal_lines[1:])) if top<=center_y<bottom),None)
        table=next((frame for frame in self.transcription.document().rootFrame().childFrames() if isinstance(frame,QTextTable)),None)
        if row is None or table is None or row>=table.rows():return
        wanted=str(name or '').casefold();matches=[]
        for column in range(table.columns()):
            cell=table.cellAt(row,column);cursor=cell.firstCursorPosition();cursor.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
            if wanted and wanted in cursor.selectedText().casefold():matches.append((column,cursor))
        if matches:
            column,cursor=matches[0];left,right=self.structure.vertical_lines[column:column+2]
            self.select_original_cell((left+right)/2,center_y)

    def highlight_suspicious(self,enabled):
        """Markiert Wörter mit gemischten Buchstaben/Ziffern, ohne sie zu verändern."""
        self.suspicious_visible=bool(enabled);document=self.transcription.document();selections=[]
        if self.name_highlight:
            cursor=document.find(self.name_highlight)
            if not cursor.isNull():
                fmt=QTextCharFormat();fmt.setBackground(QColor('#ffd54f'));fmt.setForeground(QColor('#111111'))
                extra=QTextEdit.ExtraSelection();extra.cursor=cursor;extra.format=fmt;selections.append(extra)
        if enabled:
            pattern=re.compile(r'(?iu)\b(?=[\wÄÖÜäöüßſ]*[A-Za-zÄÖÜäöüßſ])(?=[\wÄÖÜäöüßſ]*\d)[\wÄÖÜäöüßſ]+\b')
            text=self.transcription.toPlainText()
            for match in pattern.finditer(text):
                cursor=QTextCursor(document);cursor.setPosition(match.start());cursor.setPosition(match.end(),QTextCursor.MoveMode.KeepAnchor)
                fmt=QTextCharFormat();fmt.setBackground(QColor('#ffcdd2'));fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline);fmt.setUnderlineColor(QColor('#c62828'))
                extra=QTextEdit.ExtraSelection();extra.cursor=cursor;extra.format=fmt;selections.append(extra)
            self.setWindowTitle(f'Ganze Seite lesen — {self.image_path.name} — {max(0,len(selections)-(1 if self.name_highlight else 0))} verdächtige Stelle(n)')
        else:self.setWindowTitle(f'Ganze Seite lesen — {self.image_path.name}')
        self.transcription.setExtraSelections(selections)

    def toggle_fullscreen(self,enabled):
        self.showFullScreen() if enabled else self.showNormal()

    def copy_text(self):
        QApplication.clipboard().setText(self.transcription.toPlainText());self.parent().statusBar().showMessage('Transkription kopiert.',2500) if isinstance(self.parent(),QMainWindow) else None

    def save_correction(self,silent=False):
        if not self.corrected_path:
            self.export_text();return
        try:
            self.corrected_path.parent.mkdir(parents=True,exist_ok=True)
            self.corrected_path.write_text(self.transcription.toPlainText(),encoding='utf-8')
            html_path=self._corrected_html_path();html_path.write_text(self.transcription.toHtml(),encoding='utf-8')
            raw=self.raw_text_path.read_text(encoding='utf-8-sig',errors='replace') if self.raw_text_path and self.raw_text_path.exists() else ''
            pair={'image':str(self.image_path),'alto':str(self.alto_path or ''),'ocr_text':raw,'corrected_text':self.transcription.toPlainText(),'status':'gesammelt_nicht_trainiert'}
            self._training_pair_path().write_text(json.dumps(pair,ensure_ascii=False,indent=2),encoding='utf-8')
            training_alto=self.save_training_alto()
            if not silent:QMessageBox.information(self,'Transkription gespeichert',f'Die korrigierte Tabelle wurde dauerhaft gespeichert:\n{html_path}\n\n'+('Kraken-Ground-Truth wurde für das Modelltraining angelegt.' if training_alto else 'Für diese Seite konnte noch keine zeilenbezogene Ground-Truth angelegt werden.'))
        except Exception as exc:QMessageBox.critical(self,'Speichern fehlgeschlagen',str(exc))

    def export_text(self):
        suggested=self.image_path.with_suffix('.txt').name
        path,_=QFileDialog.getSaveFileName(self,'Transkription als TXT speichern',suggested,'Textdateien (*.txt)')
        if not path:return
        try:Path(path).write_text(self.transcription.toPlainText(),encoding='utf-8')
        except Exception as exc:QMessageBox.critical(self,'Speichern fehlgeschlagen',str(exc))

class DraggableSeparator(QGraphicsLineItem):
    """Eine ausschließlich horizontal oder vertikal verschiebbare Rasterlinie."""
    def __init__(self,orientation,position,width,height,changed_callback=None,start=None,end=None):
        super().__init__();self.orientation=orientation;self.changed_callback=changed_callback
        self.limit=height if orientation=='h' else width;self.length_limit=width if orientation=='h' else height
        self.start=0 if start is None else start;self.end=self.length_limit if end is None else end
        self.update_line()
        self.setPos(0,position) if orientation=='h' else self.setPos(position,0)
        self.setPen(QPen(QColor('#e62d2d' if orientation=='h' else '#146ee6'),4))
        self.setZValue(20);self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges,True)
        self.setCursor(Qt.CursorShape.SizeVerCursor if orientation=='h' else Qt.CursorShape.SizeHorCursor)
    def shape(self):
        stroker=QPainterPathStroker();stroker.setWidth(18);return stroker.createStroke(super().shape())
    def paint(self,painter,option,widget=None):
        pen=QPen(QColor('#ff8a00') if self.isSelected() else QColor('#e62d2d' if self.orientation=='h' else '#146ee6'),7 if self.isSelected() else 4)
        painter.setPen(pen);painter.drawLine(self.line())
    def itemChange(self,change,value):
        if change==QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return QPointF(0,max(0,min(self.limit,value.y()))) if self.orientation=='h' else QPointF(max(0,min(self.limit,value.x())),0)
        result=super().itemChange(change,value)
        if change==QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.changed_callback:self.changed_callback()
        return result
    def coordinate(self):return round(self.pos().y() if self.orientation=='h' else self.pos().x())
    def update_line(self):
        self.start=max(0,min(self.length_limit,round(self.start)));self.end=max(self.start+1,min(self.length_limit,round(self.end)))
        self.setLine(self.start,0,self.end,0) if self.orientation=='h' else self.setLine(0,self.start,0,self.end)
    def set_endpoint(self,which,value):
        if which=='start':self.start=min(value,self.end-1)
        else:self.end=max(value,self.start+1)
        self.update_line()

class TableEditView(ScanView):
    def __init__(self,image_path,structure,changed_callback=None):
        super().__init__();self.structure=structure;self.changed_callback=changed_callback;self.add_orientation=None;self.extent_mode=None;self.separators=[];self.dragging_separator=None;self.dragging_endpoint=None
        self.show_image(image_path);self.reload_lines()
    def reload_lines(self):
        for item in self.separators:self.scene.removeItem(item)
        self.separators=[]
        for orientation,positions in (('h',self.structure.horizontal_lines),('v',self.structure.vertical_lines)):
            for position in positions:
                extents=(self.structure.horizontal_extents if orientation=='h' else self.structure.vertical_extents) or {}
                start,end=extents.get(str(position),[0,self.structure.image_width if orientation=='h' else self.structure.image_height])
                item=DraggableSeparator(orientation,position,self.structure.image_width,self.structure.image_height,self.changed_callback,start,end)
                self.scene.addItem(item);self.separators.append(item)
        self.scene.update();self.viewport().update()
    def begin_add(self,orientation):
        self.add_orientation=orientation;self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setCursor(Qt.CursorShape.CrossCursor)
    def begin_extent(self,which):
        if not any(item.isSelected() for item in self.separators):return False
        self.extent_mode=which;self.setDragMode(QGraphicsView.DragMode.NoDrag);self.setCursor(Qt.CursorShape.CrossCursor);return True
    def mousePressEvent(self,event):
        if self.extent_mode and event.button()==Qt.MouseButton.LeftButton:
            selected=next((item for item in self.separators if item.isSelected()),None);point=self.mapToScene(event.position().toPoint())
            if selected:selected.set_endpoint(self.extent_mode,point.x() if selected.orientation=='h' else point.y())
            self.extent_mode=None;self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag);self.unsetCursor();self.apply_to_structure()
            if self.changed_callback:self.changed_callback()
            event.accept();return
        if self.add_orientation and event.button()==Qt.MouseButton.LeftButton:
            point=self.mapToScene(event.position().toPoint());position=point.y() if self.add_orientation=='h' else point.x()
            item=DraggableSeparator(self.add_orientation,position,self.structure.image_width,self.structure.image_height,self.changed_callback)
            self.scene.addItem(item);self.separators.append(item);self.add_orientation=None
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag);self.unsetCursor()
            if self.changed_callback:self.changed_callback()
            event.accept();return
        if event.button()==Qt.MouseButton.LeftButton:
            point=self.mapToScene(event.position().toPoint())
            scale=max(abs(self.transform().m11()),abs(self.transform().m22()),0.01)
            tolerance=12.0/scale
            candidates=[]
            for item in self.separators:
                distance=abs(point.y()-item.coordinate()) if item.orientation=='h' else abs(point.x()-item.coordinate())
                if distance<=tolerance:candidates.append((distance,item))
            if candidates:
                chosen=min(candidates,key=lambda candidate:candidate[0])[1]
                self.scene.clearSelection();chosen.setSelected(True);self.setFocus()
                axis=point.x() if chosen.orientation=='h' else point.y()
                endpoint_tolerance=16.0/scale
                if abs(axis-chosen.start)<=endpoint_tolerance:self.dragging_endpoint=(chosen,'start')
                elif abs(axis-chosen.end)<=endpoint_tolerance:self.dragging_endpoint=(chosen,'end')
                else:self.dragging_separator=chosen
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
                event.accept();return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.dragging_endpoint is not None:
            item,which=self.dragging_endpoint;point=self.mapToScene(event.position().toPoint())
            item.set_endpoint(which,point.x() if item.orientation=='h' else point.y())
            if self.changed_callback:self.changed_callback()
            event.accept();return
        if self.dragging_separator is not None:
            point=self.mapToScene(event.position().toPoint());item=self.dragging_separator
            if item.orientation=='h':item.setPos(0,max(0,min(item.limit,point.y())))
            else:item.setPos(max(0,min(item.limit,point.x())),0)
            if self.changed_callback:self.changed_callback()
            event.accept();return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if self.dragging_endpoint is not None:
            self.dragging_endpoint=None;self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag);self.apply_to_structure()
            if self.changed_callback:self.changed_callback()
            event.accept();return
        if self.dragging_separator is not None:
            self.dragging_separator=None;self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag);self.apply_to_structure()
            if self.changed_callback:self.changed_callback()
            event.accept();return
        super().mouseReleaseEvent(event)
    def contextMenuEvent(self,event):
        point=self.mapToScene(event.pos());scale=max(abs(self.transform().m11()),abs(self.transform().m22()),0.01);tolerance=12.0/scale
        horizontal=next((item for item in self.separators if item.orientation=='h' and abs(point.y()-item.coordinate())<=tolerance),None)
        vertical=next((item for item in self.separators if item.orientation=='v' and abs(point.x()-item.coordinate())<=tolerance),None)
        menu=QMenu(self)
        add_row=menu.addAction('Zeile hinzufügen')
        remove_row=menu.addAction('Zeile entfernen');remove_row.setEnabled(horizontal is not None)
        menu.addSeparator()
        add_column=menu.addAction('Spalte hinzufügen')
        remove_column=menu.addAction('Spalte entfernen');remove_column.setEnabled(vertical is not None)
        chosen=menu.exec(event.globalPos())
        if chosen==add_row:self.add_separator_at('h',point.y())
        elif chosen==remove_row:self.remove_separator(horizontal)
        elif chosen==add_column:self.add_separator_at('v',point.x())
        elif chosen==remove_column:self.remove_separator(vertical)
    def add_separator_at(self,orientation,position):
        item=DraggableSeparator(orientation,position,self.structure.image_width,self.structure.image_height,self.changed_callback)
        self.scene.addItem(item);self.separators.append(item);self.apply_to_structure()
        if self.changed_callback:self.changed_callback()
    def remove_separator(self,item):
        if item is None:return
        self.scene.removeItem(item);self.separators.remove(item);self.apply_to_structure()
        if self.changed_callback:self.changed_callback()
    def delete_selected(self):
        selected=[item for item in self.separators if item.isSelected()]
        for item in selected:self.scene.removeItem(item);self.separators.remove(item)
        if selected:
            self.apply_to_structure()
            if self.changed_callback:self.changed_callback()
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace):self.delete_selected();event.accept();return
        super().keyPressEvent(event)
    def apply_to_structure(self):
        self.structure.horizontal_lines=[item.coordinate() for item in self.separators if item.orientation=='h']
        self.structure.vertical_lines=[item.coordinate() for item in self.separators if item.orientation=='v']
        self.structure.horizontal_extents={str(item.coordinate()):[item.start,item.end] for item in self.separators if item.orientation=='h'}
        self.structure.vertical_extents={str(item.coordinate()):[item.start,item.end] for item in self.separators if item.orientation=='v'}
        return rebuild_cells(self.structure)

class TableStructureDialog(QDialog):
    def __init__(self,image_path,overlay_path,structure,json_path=None,parent=None):
        super().__init__(parent);self.structure=structure;self.json_path=Path(json_path) if json_path else None;self.image_path=Path(image_path)
        self.setWindowTitle(f'Tabellenstruktur bearbeiten — {Path(image_path).name}');self.resize(1180,850);self.setMinimumSize(760,560)
        layout=QVBoxLayout(self)
        self.info=QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        tools=QHBoxLayout()
        redetect=QPushButton('Raster neu erkennen');redetect.setToolTip('Verwirft nur die aktuelle Rasteranzeige und erkennt die Linien dieser Seite erneut.');redetect.clicked.connect(self.redetect);tools.addWidget(redetect)
        add_row=QPushButton('Neue Zeilengrenze');add_row.clicked.connect(lambda:self.start_add('h'));tools.addWidget(add_row)
        add_column=QPushButton('Neue Spaltengrenze');add_column.clicked.connect(lambda:self.start_add('v'));tools.addWidget(add_column)
        delete=QPushButton('Ausgewählte Linie löschen');delete.setToolTip('Waagerechte oder senkrechte Linie anklicken und dann löschen. Entf-Taste funktioniert ebenfalls.');delete.clicked.connect(self.delete_selected);tools.addWidget(delete);tools.addStretch();layout.addLayout(tools)
        extents=QHBoxLayout();extents.addWidget(QLabel('Linienlänge:'))
        start=QPushButton('Anfang im Bild setzen');start.clicked.connect(lambda:self.start_extent('start'));extents.addWidget(start)
        end=QPushButton('Ende im Bild setzen');end.clicked.connect(lambda:self.start_extent('end'));extents.addWidget(end);extents.addStretch();layout.addLayout(extents)
        self.view=TableEditView(image_path,structure,self.update_info);layout.addWidget(self.view,1)
        row=QHBoxLayout();row.addStretch();cancel=QPushButton('Abbrechen');cancel.clicked.connect(self.reject);row.addWidget(cancel)
        save=QPushButton('Raster speichern');save.setObjectName('primary');save.clicked.connect(self.save);row.addWidget(save);layout.addLayout(row)
        self.update_info()
        QTimer.singleShot(0,self.view.fit)
    def update_info(self):
        structure=self.view.apply_to_structure() if hasattr(self,'view') else self.structure
        self.info.setText(f'Rot = Zeilengrenzen, Blau = Spaltengrenzen. Linie mittig mit links verschieben; Linienende mit links ziehen, um die Länge zu ändern. Rechtsklick: Zeile oder Spalte hinzufügen/entfernen. '
                          f'Aktuell: {len(structure.horizontal_lines)} Zeilengrenzen, {len(structure.vertical_lines)} Spaltengrenzen, {len(structure.cells)} Zellen.')
    def redetect(self):
        fresh=detect_table_structure(self.image_path);self.structure=fresh;self.view.structure=fresh;self.view.reload_lines();self.view.fit();self.update_info()
        if len(fresh.horizontal_lines)<2 or len(fresh.vertical_lines)<2:
            QMessageBox.warning(self,'Raster neu erkennen','Auch bei der neuen Erkennung wurde kein vollständiges Raster gefunden. Linien können mit Rechtsklick oder den Schaltflächen manuell hinzugefügt werden.')
    def start_add(self,orientation):
        self.view.begin_add(orientation);self.info.setText(('Bitte jetzt an der gewünschten Höhe' if orientation=='h' else 'Bitte jetzt an der gewünschten Spaltenposition')+' in das Original klicken.')
    def delete_selected(self):self.view.delete_selected()
    def start_extent(self,which):
        if not self.view.begin_extent(which):QMessageBox.information(self,'Linienlänge','Bitte zuerst eine rote oder blaue Linie anklicken.')
        else:self.info.setText('Jetzt an die gewünschte Position für '+('den Linienanfang' if which=='start' else 'das Linienende')+' klicken.')
    def save(self):
        structure=self.view.apply_to_structure()
        if self.json_path:save_structure(structure,self.json_path)
        self.accept()

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
        # RC9: aufgeräumte Navigation und dokumentbezogene Werkzeuge.
        super().__init__();self.setWindowTitle('ArchivAgent 7.1 RC19');self.resize(1220,800);self.setMinimumSize(980,680);self.thread=None;self.worker=None;self.pending_result=None;self.pending_full_read=None;self.last_imported_image=None;self.current_image_index=-1;self.current_images=[];self.current_hit=None;self.current_auto_bbox=None;self.current_position_key=None;self.all_hit_rows=[];self.hit_ratings={};self.last_rating_action=None
        self.base=QLineEdit(BASE_DEFAULT);self.project=QComboBox();self.project.setEditable(True);self.book=QComboBox();self.book.setEditable(True);self.url=QLineEdit();self.names=QLineEdit();self.start=QSpinBox();self.start.setRange(1,999999);self.start.setValue(1);self.start.setSingleStep(1);self.start.setAccelerated(True);self.start.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons);self.end=QSpinBox();self.end.setRange(0,999999);self.end.setValue(0);self.end.setSingleStep(1);self.end.setAccelerated(True);self.end.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons);self.threshold=QDoubleSpinBox();self.threshold.setRange(.5,1);self.threshold.setValue(.72);self.threshold.setSingleStep(.01);self.threshold.setDecimals(2);self.threshold.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons);self.force=QCheckBox('Vorhandene Texterkennung erneut ausführen');self.log=QPlainTextEdit();self.log.setReadOnly(True);self.progress=QProgressBar();self.stats={};self.hit_rows=[];self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['Status','Name','Buch','Seite','Übereinstimmung','Textumgebung','Quelle']);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.scan_view=ScanView();self.scan_view.save_marker_callback=self.save_current_marker;self.scan_view.reset_marker_callback=self.reset_current_marker;self.scan_view.marker_changed_callback=self.marker_moved;self.scan_title=QLabel('Kein Treffer ausgewählt');self.scan_title.setWordWrap(True);self.page_label=QLabel('Seite – / –');self.ocr_title=QLabel('Erkannter Text');self.ocr_title.setFont(QFont('Segoe UI',11,QFont.Weight.Bold));self.ocr_text=QTextEdit();self.ocr_text.setReadOnly(True);self.ocr_text.setPlaceholderText('Zu diesem Treffer wurde noch kein erkannter Text gefunden.');self.ocr_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth);self.book_table=QTableWidget(0,5);self.book_table.setHorizontalHeaderLabels(['Buch','Seiten','Heruntergeladen','Text erkannt','Treffer']);self.book_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setWindowTitle('ArchivAgent 7.1 RC19')
        self.nav=QListWidget();self.nav.addItems(['Buch durchsuchen','Bücher','Treffer prüfen','Einstellungen','Info']);self.nav.setFixedWidth(220);self.stack=QStackedWidget()
        for w in [self.search_page(),self.books_page(),self.hits_page(),self.settings_page(),self.info_page()]:self.stack.addWidget(w)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex);self.nav.currentRowChanged.connect(self.navigation_changed)
        sp=QSplitter();sp.addWidget(self.nav);sp.addWidget(self.stack);sp.setStretchFactor(1,1);self.setCentralWidget(sp);self.toolbar();self.style();self.refresh();self.nav.setCurrentRow(0)
    def head(self,t,s):
        w=QWidget();l=QVBoxLayout(w);h=QLabel(t);h.setFont(QFont('Segoe UI',22,QFont.Weight.Bold));x=QLabel(s);x.setWordWrap(True);l.addWidget(h);l.addWidget(x);return w
    def navigation_changed(self,row):
        self.refresh()
        if row==2 and self.hit_rows:
            self.table.selectRow(0);QTimer.singleShot(0,lambda:self.open_selected_hit_page(0,0))
    def select_box(self):
        g=QGroupBox('Auswahl');f=QFormLayout(g);f.addRow('Projekt',self.project);f.addRow('Buch',self.book);self.project.currentTextChanged.connect(self.refresh_books);return g
    def dashboard(self):
        w=QWidget();l=QVBoxLayout(w);l.addWidget(self.head('ArchivAgent 7.1 RC19','Online-Archive und eigene Scans lesen, nach Familiennamen suchen und Ergebnisse prüfen.'));g=QGridLayout()
        for i,k in enumerate(['Projekte','Bücher','Scans','Treffer']):
            c=QFrame();c.setObjectName('card');cl=QVBoxLayout(c);a=QLabel(k);a.setFont(QFont('Segoe UI',12,QFont.Weight.Bold));v=QLabel('0');v.setFont(QFont('Segoe UI',25,QFont.Weight.Bold));self.stats[k]=v;cl.addWidget(a);cl.addWidget(v);g.addWidget(c,i//2,i%2)
        l.addLayout(g);l.addStretch();return w
    def info_page(self):
        w=QWidget();l=QVBoxLayout(w);l.addWidget(self.head('Info','Informationen zu ArchivAgent.'))
        info=QLabel('<b>ArchivAgent</b><br><br>Version: 7.1 RC19<br>Release: August 2026<br><br>'
                    'Programmierer: Frank Bernbeck<br><br>'
                    'Werkzeug zum Durchsuchen, Lesen und Korrigieren historischer Handschriften.<br><br>'
                    'Lizenz: GPL-3.0<br>Handschriftenmodell: Stefan Weil, CC BY-SA 4.0')
        info.setWordWrap(True);info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        l.addWidget(info);l.addStretch();return w
    def search_page(self):
        w=QWidget();l=QVBoxLayout(w)
        l.addWidget(self.head('Buch durchsuchen','Buchseiten herunterladen, Schrift erkennen und nach Familiennamen durchsuchen.'))
        g=QGroupBox('Suchmaske');f=QFormLayout(g)
        f.addRow('Projekt',self.project)
        f.addRow('Buch',self.book)
        self.project.currentTextChanged.connect(self.refresh_books)
        f.addRow('Suchbegriffe / Namen',self.names)
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
        hint=QLabel('Mehrere Suchbegriffe oder Namen bitte mit Komma trennen, zum Beispiel: Müller, Schmied, Testament.');hint.setWordWrap(True);f.addRow('',hint)
        l.addWidget(g)
        r=QGridLayout()
        a=QPushButton('Alles automatisch starten');a.setObjectName('primary');a.clicked.connect(lambda:self.start_task('all'))
        i=QPushButton('Eigene Scans/Bilder hinzufügen');i.clicked.connect(self.import_own_images)
        h=QPushButton('Vorhandenes Buch/Scan durchsuchen');h.clicked.connect(lambda:self.start_task('htr'))
        c=QPushButton('Abbrechen');c.clicked.connect(self.cancel)
        for index,button in enumerate((a,i,h,c)):r.addWidget(button,index,0)
        l.addLayout(r)
        self.document_tools=QGroupBox('Geladenes Dokument bearbeiten');document_layout=QHBoxLayout(self.document_tools)
        self.read_button=QPushButton('Dokument vollständig lesen');self.read_button.clicked.connect(self.read_own_document)
        self.book_reader_button=QPushButton('Ganzes Buch anzeigen');self.book_reader_button.clicked.connect(self.show_whole_book)
        self.table_button=QPushButton('Tabellenstruktur zuweisen / bearbeiten');self.table_button.clicked.connect(self.detect_current_table)
        self.table_button.setToolTip('Bitte zuerst die erste Seite auswählen, auf der die Tabelle tatsächlich beginnt.')
        self.train_button=QPushButton('Persönliches Kraken-Modell trainieren');self.train_button.clicked.connect(self.train_personal_model)
        document_layout.addWidget(self.read_button);document_layout.addWidget(self.book_reader_button);document_layout.addWidget(self.table_button);document_layout.addWidget(self.train_button);document_layout.addStretch()
        self.document_tools.setVisible(False);l.addWidget(self.document_tools)
        l.addWidget(self.task_panel())
        w.setMinimumHeight(820)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setWidget(w);return scroll


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
        w=QWidget();l=QVBoxLayout(w);l.addWidget(self.head('Trefferseiten','Treffer auswählen – die vollständige Originalseite und Transkription öffnen sich sofort.'))
        review=QHBoxLayout()
        self.hit_filter=QComboBox();self.hit_filter.addItems(['Offene Treffer','Alle Treffer','Bestätigte Treffer','Verworfene Treffer']);self.hit_filter.currentIndexChanged.connect(self.apply_hit_filter)
        confirm=QPushButton('✓ Bestätigen');confirm.clicked.connect(lambda:self.rate_current_hit('confirmed'))
        reject=QPushButton('✗ Verwerfen');reject.clicked.connect(lambda:self.rate_current_hit('rejected'))
        restore=QPushButton('↺ Als offen markieren');restore.clicked.connect(lambda:self.rate_current_hit('open'))
        self.review_status=QLabel('Offen: 0   Bestätigt: 0   Verworfen: 0')
        review.addWidget(QLabel('Anzeige'));review.addWidget(self.hit_filter);review.addSpacing(12);review.addWidget(confirm);review.addWidget(reject);review.addWidget(restore);review.addStretch();review.addWidget(self.review_status);l.addLayout(review)
        r=QHBoxLayout();b=QPushButton('Treffer neu laden');b.clicked.connect(self.load_hits);h=QPushButton('Bericht öffnen');h.clicked.connect(self.open_report)
        r.addWidget(b);r.addWidget(h);r.addStretch();l.addLayout(r);l.addWidget(self.table,1)
        self.position_status=QLabel('Position: –')
        self.table.cellClicked.connect(self.open_selected_hit_page);return w

    def open_selected_hit_page(self,row,column=0):
        """Ein Treffer öffnet sofort die vollständige Seite samt Transkription."""
        self.preview_hit(row,column)
        if 0<=row<len(self.hit_rows):self.read_current_hit_page()
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
        has_document=bool(self.project.currentText().strip() and self.book.currentText().strip() and self.bkd().exists() and find_images(self.bkd()))
        if hasattr(self,'document_tools'):self.document_tools.setVisible(has_document)
        if not hasattr(self,'bookinfo'):return
        if hasattr(self,'current_selection'):self.current_selection.setText(f'Aktuelle Auswahl: {self.project.currentText()}  →  {self.book.currentText()}')
        d=self.bkd();imgs=find_images(d) if d.exists() else [];s=f'Buchordner: {d}\nScans: {len(imgs)}\n';q=d/'quelle.txt';s+=('\n'+q.read_text(encoding='utf-8',errors='replace')) if q.exists() else '';self.bookinfo.setPlainText(s)
    def update_stats(self):
        d=self.bd()/'Projekte';ps=[p for p in d.iterdir() if p.is_dir()] if d.exists() else [];books=scans=0
        for p in ps:
            for b in p.iterdir():
                if b.is_dir() and b.name.casefold() not in {'treffer','berichte'}:books+=1;scans+=len(find_images(b))
        vals={'Projekte':len(ps),'Bücher':books,'Scans':scans,'Treffer':len(read_hits(self.pd())) if self.project.currentText() else 0}
        for k,v in vals.items():
            if k in self.stats:self.stats[k].setText(str(v))
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

    def resolve_page_textfile(self,img):
        """Findet die vollständige Transkription einer beliebigen Buchseite."""
        img=Path(img);book_dir=img.parent.parent if img.parent.name.casefold() in {'originalseiten','scans'} else img.parent
        candidates=[
            img.with_suffix('.txt'),book_dir/'HTR'/'Texte'/f'{img.stem}.txt',
            book_dir/'HTR'/f'{img.stem}.txt',book_dir/'OCR'/'Texte'/f'{img.stem}.txt',
            book_dir/'OCR'/f'{img.stem}.txt',book_dir/'Texte'/f'{img.stem}.txt',
        ]
        return next((path for path in candidates if path.exists() and path.is_file() and path.stat().st_size > 0),None)

    def resolve_page_layoutfile(self,img):
        img=Path(img);book_dir=img.parent.parent if img.parent.name.casefold() in {'originalseiten','scans'} else img.parent
        candidates=[book_dir/'HTR'/'Layout'/f'{img.stem}.txt',book_dir/'OCR'/'Layout'/f'{img.stem}.txt']
        return next((path for path in candidates if path.exists() and path.is_file() and path.stat().st_size > 0),None)

    def resolve_page_structurefile(self,img):
        img=Path(img);book_dir=img.parent.parent if img.parent.name.casefold() in {'originalseiten','scans'} else img.parent
        candidates=[book_dir/'HTR'/'Struktur'/f'{img.stem}.json',book_dir/'OCR'/'Struktur'/f'{img.stem}.json']
        return next((path for path in candidates if path.exists() and path.is_file()),None)

    def resolve_page_altofile(self,img):
        img=Path(img);book_dir=img.parent.parent if img.parent.name.casefold() in {'originalseiten','scans'} else img.parent
        candidates=[book_dir/'HTR'/'ALTO'/f'{img.stem}.xml',book_dir/'OCR'/'ALTO'/f'{img.stem}.xml']
        return next((path for path in candidates if path.exists() and path.is_file()),None)

    def open_page_reader(self,img,text_path=None,highlight='',bbox=None):
        if not img or not Path(img).exists():
            QMessageBox.warning(self,'Ganze Seite lesen','Die Originalseite wurde nicht gefunden.');return
        text_path=self.resolve_page_layoutfile(img) or (Path(text_path) if text_path else self.resolve_page_textfile(img))
        structure_path=self.resolve_page_structurefile(img)
        alto_path=self.resolve_page_altofile(img)
        dialog=FullPageReader(Path(img),text_path,highlight,bbox,structure_path,alto_path,self);dialog.exec()

    def show_whole_book(self):
        """Blättert durch alle importierten Seiten mit Raster und Tabellentext."""
        images=find_images(self.bkd())
        if not images:
            QMessageBox.information(self,'Ganzes Buch anzeigen','Für dieses Buch wurden noch keine Seiten importiert.');return
        requested=self.start.value();index=next((i for i,image in enumerate(images) if image_page_number(image)==requested),0)
        while 0<=index<len(images):
            image=images[index]
            dialog=FullPageReader(
                image,self.resolve_page_layoutfile(image) or self.resolve_page_textfile(image),'',None,
                self.resolve_page_structurefile(image),self.resolve_page_altofile(image),self,
                can_previous=index>0,can_next=index<len(images)-1,
            )
            dialog.exec()
            if not dialog.navigation_delta:break
            index+=dialog.navigation_delta

    def read_current_hit_page(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.hit_rows):
            QMessageBox.information(self,'Ganze Trefferseite lesen','Bitte zuerst einen Treffer auswählen.');return
        hit=self.hit_rows[row];img=self.resolve_hit_image(hit);bbox=None
        if img:
            saved=self.saved_bbox(hit,img)
            bbox=saved or self.estimated_line_bbox(hit,img)[0]
        self.open_page_reader(img,self.resolve_hit_textfile(hit,img),hit.get('name',''),bbox)

    def show_hit_text(self,h,img=None):
        self.ocr_text.clear();self.ocr_title.setText('Erkannter Text')
        structure_path=self.resolve_page_structurefile(img) if img else None
        alto_path=self.resolve_page_altofile(img) if img else None
        rendered_table=False
        if structure_path and alto_path:
            try:
                self.ocr_text.setHtml(transcription_html_from_grid(alto_path,load_structure(structure_path)))
                self.ocr_title.setText('Erkannter Text — als Tabelle nach dem Original')
                txt=None;rendered_table=True
            except Exception:
                txt=self.resolve_hit_textfile(h,img)
        else:txt=self.resolve_hit_textfile(h,img)
        if not txt and not rendered_table:
            self.ocr_text.setPlainText('Für diesen Treffer wurde keine passende Textdatei gefunden.\n\nDie Originalseite kann trotzdem geprüft werden.')
            return
        if txt:
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
            structure_path=self.resolve_page_structurefile(img)
            if structure_path:
                try:self.scan_view.show_structure(load_structure(structure_path))
                except Exception:pass
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
        p={'base':str(self.bd()),'project':self.project.currentText().strip(),'book':self.book.currentText().strip(),'url':self.url.text().strip(),'start':start_page,'end':end_page,'limit':page_limit,'threshold':self.threshold.value(),'force':self.force.isChecked(),'names':self.names.text().strip(),'read_only':a=='read'}
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
            if ok and self.pending_full_read:
                QTimer.singleShot(150,self.open_pending_full_read)
            elif not ok:
                self.pending_full_read=None
        except Exception as e:
            write_crash_log('Fehler in thread_done',e)
            QMessageBox.critical(self,'ArchivAgent',f'Abschlussfehler: {e}\n\nDetails stehen in archivagent_crash.log.')
    def safe_finish_refresh(self):
        try:self.refresh()
        except Exception as e:
            self.log.appendPlainText(f'[ABSCHLUSS-FEHLER] {e}')
            write_crash_log('Fehler beim Abschluss-Refresh',e)
    def open_pending_full_read(self):
        img=self.pending_full_read;self.pending_full_read=None
        if img:self.open_page_reader(img)
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
            self.last_imported_image=imported[0] if len(imported)==1 else None
            first=image_page_number(imported[0]) or 1;last=image_page_number(imported[-1]) or first
            self.start.setValue(first);self.end.setValue(last);self.url.clear();self.refresh()
            self.project.setCurrentText(project);self.refresh_books();self.book.setCurrentText(book);self.update_book()
            QMessageBox.information(
                self,'Bilder hinzugefügt',
                f'{len(imported)} Bilddatei(en) wurden in Originalseiten eingefügt und als '
                f'Seite {first} bis {last} nummeriert.\n\n'
                'Für die Namenssuche anschließend Familiennamen eintragen und „Alles automatisch starten“ wählen.\n\n'
                'Für eine vollständige Transkription ohne Namenssuche jetzt „Dokument vollständig lesen“ wählen.'
            )
        except Exception as exc:
            write_crash_log('Fehler beim Import eigener Bilder',exc)
            QMessageBox.critical(self,'Import fehlgeschlagen',str(exc))
    def read_own_document(self):
        project=self.project.currentText().strip();book=self.book.currentText().strip()
        if not project or not book:
            QMessageBox.warning(self,'Dokument vollständig lesen','Bitte zuerst Projekt und Buch angeben.');return
        try:
            image=Path(self.last_imported_image) if self.last_imported_image and Path(self.last_imported_image).exists() else None
            available=find_images(self.bkd())
            if image not in available:image=None
            if image is None and len(available)==1:image=available[0]
            if image is None:
                selected,_=QFileDialog.getOpenFileName(
                    self,'Bereits importierte Seite auswählen',str(self.bkd()/'Originalseiten'),
                    'Bilddateien (*.png *.jpg *.jpeg *.tif *.tiff *.jp2 *.webp)'
                )
                if not selected:return
                candidate=Path(selected)
                if candidate not in available:
                    QMessageBox.warning(self,'Dokument vollständig lesen','Bitte eine bereits über „Eigene Scans/Bilder hinzufügen“ importierte Seite auswählen.');return
                image=candidate
            page=image_page_number(image) or 1
            self.start.setValue(page);self.end.setValue(page);self.url.clear()
            self.pending_full_read=image
            self.log.appendPlainText(f'[LESEMODUS] {image.name} wird vollständig geprüft und bei Bedarf neu transkribiert; eine Namenseingabe ist nicht erforderlich.')
            self.start_task('read')
        except Exception as exc:
            self.pending_full_read=None;write_crash_log('Fehler im vollständigen Lesemodus',exc);QMessageBox.critical(self,'Lesemodus fehlgeschlagen',str(exc))
    def selected_imported_image(self,title):
        image=Path(self.last_imported_image) if self.last_imported_image and Path(self.last_imported_image).exists() else None
        available=find_images(self.bkd())
        if image not in available:image=None
        if image is None and available:
            requested=self.start.value()
            image=next((candidate for candidate in available if image_page_number(candidate)==requested),None)
        if image is None and len(available)==1:image=available[0]
        if image is None:
            selected,_=QFileDialog.getOpenFileName(self,title,str(self.bkd()/'Originalseiten'),'Bilddateien (*.png *.jpg *.jpeg *.tif *.tiff *.jp2 *.webp)')
            if not selected:return None
            candidate=Path(selected)
            if candidate not in available:
                QMessageBox.warning(self,title,'Bitte eine bereits importierte Seite auswählen.');return None
            image=candidate
        return image
    def select_table_page(self):
        """Lässt die erste echte Registerseite ausdrücklich auswählen.

        Umschlag, Vorsatz und Inhaltsseiten dürfen nicht versehentlich als
        Tabellenraster des Buches behandelt werden. Deshalb wird hier nicht
        stillschweigend die zuletzt importierte (oft erste) Seite verwendet.
        """
        available=find_images(self.bkd())
        if not available:
            QMessageBox.warning(self,'Tabellenstruktur erkennen','Für dieses Buch wurden noch keine Seiten importiert.');return None
        labels=[]
        for index,image in enumerate(available,1):
            page=image_page_number(image) or index
            labels.append(f'Seite {page} — {image.name}')
        requested=self.start.value()
        initial=next((index for index,image in enumerate(available) if image_page_number(image)==requested),0)
        label,accepted=QInputDialog.getItem(
            self,'Erste Tabellenseite auswählen',
            'Auf welcher Seite beginnt die Tabelle?\nUmschlag- und Vorsatzseiten bleiben ohne Raster.',
            labels,initial,False
        )
        if not accepted:return None
        return available[labels.index(label)]
    def detect_current_table(self):
        project=self.project.currentText().strip();book=self.book.currentText().strip()
        if not project or not book:
            QMessageBox.warning(self,'Tabellenstruktur erkennen','Bitte zuerst Projekt und Buch angeben.');return
        image=self.select_table_page()
        if not image:return
        try:
            folder=self.bkd()/'HTR'/'Struktur';json_path=folder/f'{image.stem}.json';overlay_path=folder/f'{image.stem}_Raster.png'
            structure=load_structure(json_path) if json_path.exists() else None
            # Ein früherer Versuch auf Umschlag/Vorsatz kann eine leere JSON-Datei
            # hinterlassen. Sie darf eine neue Erkennung der echten Tabellenseite
            # nicht blockieren.
            if structure is None or len(structure.horizontal_lines)<2 or len(structure.vertical_lines)<2:
                structure=detect_table_structure(image)
                save_structure(structure,json_path)
            draw_structure_overlay(image,structure,overlay_path)
            if len(structure.horizontal_lines)<2 or len(structure.vertical_lines)<2:
                QMessageBox.warning(self,'Tabellenstruktur erkennen','Es wurde noch kein vollständiges Tabellenraster erkannt. Die erkannten Linien werden trotzdem zur Prüfung angezeigt.')
            dialog=TableStructureDialog(image,overlay_path,structure,json_path,self)
            if dialog.exec()==QDialog.DialogCode.Accepted:
                structure=load_structure(json_path)
                answer=QMessageBox.question(
                    self,'Tabellenraster als Buchvorlage verwenden',
                    f'Soll dieses Raster ab {image.name} auf alle folgenden Buchseiten übertragen werden?\n\nUmschlag- und Vorsatzseiten davor bleiben ohne Tabelle.',
                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if answer==QMessageBox.StandardButton.Yes:
                    count=self.apply_table_template(image,structure)
                    QMessageBox.information(self,'Buchraster gespeichert',f'Die Tabellenstruktur wurde für {count} Seite(n) ab der gewählten Startseite gespeichert. Sie erscheint jetzt beim Durchblättern und bei Treffern.')
        except Exception as exc:
            write_crash_log('Fehler bei der Tabellenerkennung',exc);QMessageBox.critical(self,'Tabellenerkennung fehlgeschlagen',str(exc))

    def apply_table_template(self,start_image,structure):
        images=find_images(self.bkd())
        try:start_index=images.index(Path(start_image))
        except ValueError:return 0
        folder=self.bkd()/'HTR'/'Struktur';folder.mkdir(parents=True,exist_ok=True)
        metadata={'start_image':Path(start_image).name,'start_page':image_page_number(start_image),'source_structure':f'{Path(start_image).stem}.json'}
        (folder/'Buchvorlage.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        count=0
        for image in images[start_index:]:
            pixmap=QPixmap(str(image))
            if pixmap.isNull():continue
            target=scale_structure(structure,pixmap.width(),pixmap.height())
            save_structure(target,folder/f'{image.stem}.json');count+=1
        return count

    def train_personal_model(self):
        """Startet echtes Kraken-Fine-Tuning mit den gespeicherten Ground-Truth-Dateien."""
        if hasattr(self,'training_process') and self.training_process.state()!=QProcess.ProcessState.NotRunning:
            QMessageBox.information(self,'Modelltraining','Es läuft bereits ein Modelltraining.');return
        ground_truth=sorted((self.bd()/'Projekte').rglob('*.groundtruth.xml')) if (self.bd()/'Projekte').exists() else []
        line_count=0
        for path in ground_truth:
            try:line_count+=sum(1 for element in ET.parse(path).getroot().iter() if element.tag.rsplit('}',1)[-1]=='TextLine')
            except Exception:pass
        if not ground_truth or not line_count:
            QMessageBox.information(self,'Modelltraining','Noch keine Trainingsdaten vorhanden. Zuerst Tabellen korrigieren und „Korrektur speichern“ wählen.');return
        if line_count<100:
            answer=QMessageBox.warning(self,'Wenig Trainingsmaterial',f'Bislang liegen nur {line_count} korrigierte Textzeilen vor. Das ist für ein zuverlässiges Modell sehr wenig und kann die Erkennung sogar verschlechtern. Trotzdem echtes Fine-Tuning starten?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
        scripts=self.bd()/'runtime'/'Scripts';ketos=scripts/'ketos.exe'
        if not ketos.exists():
            QMessageBox.critical(self,'Modelltraining',f'Krakens Trainingsprogramm wurde nicht gefunden:\n{ketos}\n\nBitte den OCR-Assistenten erneut ausführen.');return
        base_models=list((self.bd()/'Models').rglob('german_handwriting.mlmodel'))
        if not base_models:base_models=list((self.bd()/'Models').rglob('*.mlmodel'))
        if not base_models:
            QMessageBox.critical(self,'Modelltraining','Das Ausgangsmodell wurde nicht gefunden.');return
        base_model=sorted(base_models,key=lambda path:path.stat().st_mtime)[0]
        output_dir=self.bd()/'Models'/'Persoenlich';output_dir.mkdir(parents=True,exist_ok=True)
        checkpoint_dir=output_dir/'checkpoints';checkpoint_dir.mkdir(parents=True,exist_ok=True)
        # Kraken 7: --load startet echtes Fine-Tuning; am Ende wird das beste
        # Checkpoint automatisch in ein verteilbares safetensors-Modell gewandelt.
        args=['train','-f','xml','--linetype','bbox','--load',str(base_model),'--resize','add',
              '--checkpoint-path',str(checkpoint_dir),'--weights-format','safetensors','--lag','5',*map(str,ground_truth)]
        self.training_dialog=QProgressDialog(f'Kraken trainiert mit {line_count} korrigierten Zeilen…','Training abbrechen',0,0,self)
        self.training_dialog.setWindowTitle('Persönliches Kraken-Modell');self.training_dialog.setWindowModality(Qt.WindowModality.NonModal);self.training_dialog.setMinimumDuration(0)
        self.training_process=QProcess(self);self.training_process.setProgram(str(ketos));self.training_process.setArguments(args);self.training_process.setWorkingDirectory(str(output_dir));self.training_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.training_process.readyReadStandardOutput.connect(self.training_output)
        self.training_process.finished.connect(self.training_finished);self.training_dialog.canceled.connect(self.training_process.kill)
        self.log.appendPlainText(f'[TRAINING] {line_count} Zeilen aus {len(ground_truth)} Seite(n); Ausgangsmodell: {base_model.name}')
        self.training_process.start()

    def training_output(self):
        text=bytes(self.training_process.readAllStandardOutput()).decode('utf-8',errors='replace').strip()
        if text:self.log.appendPlainText('[KETOS] '+text)

    def training_finished(self,exit_code,exit_status):
        self.training_dialog.close();folder=self.bd()/'Models'/'Persoenlich'
        models=sorted(list(folder.rglob('*.safetensors'))+list(folder.rglob('*.mlmodel')),key=lambda path:path.stat().st_mtime,reverse=True)
        if exit_code==0 and models:
            QMessageBox.information(self,'Modelltraining abgeschlossen',f'Das persönliche Kraken-Modell wurde erzeugt:\n{models[0]}\n\nEs wird bei der nächsten Texterkennung automatisch verwendet.')
        else:
            QMessageBox.critical(self,'Modelltraining fehlgeschlagen',f'Ketos wurde mit Fehlercode {exit_code} beendet. Die Einzelheiten stehen im Protokoll auf der Startseite.')
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
