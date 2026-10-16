"""Local, editable print designs and a private imported-template library."""
from pathlib import Path
import html
import io
import json
import uuid
import pymupdf as fitz
import qrcode
from label_engine import open_document, make_label


def design(key, name, kind, subtitle, rows):
    return dict(id=key, name=name, kind=kind, subtitle=subtitle, rows=rows)


DESIGNS = [
    design('daily', 'Daily checklist', 'check', 'Date: __________   Focus: __________',
           ['Top priority', 'Second priority', 'Third priority'] + [''] * 7),
    design('weekly', 'Weekly planner', 'week', 'Week beginning: __________________',
           ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']),
    design('shopping', 'Shopping list', 'check', 'Shop: __________   Date: __________',
           ['FOOD', '', '', '', 'HOUSEHOLD', '', '', 'OTHER', '', '']),
    design('packing', 'Packing checklist', 'check', 'Trip: __________   Date: __________',
           ['Travel documents', 'Tickets / booking details', 'Phone and charger', 'Clothes',
            'Toiletries', 'Medication', 'Keys', 'Water bottle', '', '']),
    design('cleaning', 'Cleaning checklist', 'check', 'Room: __________   Date: __________',
           ['Clear surfaces', 'Dust shelves', 'Wipe surfaces', 'Clean mirrors', 'Vacuum / sweep',
            'Mop floor', 'Empty bins', 'Replace supplies', '', '']),
    design('habits', 'Habit tracker', 'habits', 'Week beginning: __________________',
           ['Drink water', 'Move / exercise', 'Read', 'Tidy up', 'Sleep routine']),
    design('project', 'Project task list', 'check', 'Project: __________   Due: __________',
           ['Define the outcome', 'Gather materials', 'First step', 'Next step', 'Review progress',
            'Finish and check', '', '', '', '']),
    design('orders', 'Order packing checklist', 'check', 'Order: __________   Packed by: ______',
           ['Check product and quantity', 'Inspect condition', 'Include all parts', 'Protect items',
            'Add packing slip', 'Add thank-you insert', 'Check delivery label', 'Seal package',
            'Weigh parcel', 'Ready to dispatch']),
    design('stock', 'Stock count sheet', 'stock', 'Location: __________   Date: ________',
           ['Item | Expected | Actual'] + [' | | '] * 9),
    design('storage', 'Storage box label', 'fields', 'Box: __________   Location: ________',
           ['Contents', '', '', '', 'Notes']),
    design('freezer', 'Food freezer label', 'fields', 'Keep your food clearly labelled',
           ['Contents', 'Date frozen', 'Portions', 'Use by (your guidance)', 'Notes']),
    design('plants', 'Plant care label', 'fields', 'Plant: ___________________________',
           ['Watering', 'Light', 'Feeding', 'Last cared for', 'Notes']),
    design('maintenance', 'Equipment maintenance log', 'stock', 'Equipment: ______________________',
           ['Date | Work done | Next check'] + [' | | '] * 9),
    design('handling', 'Parcel handling label', 'handling', 'Thank you for handling with care',
           ['FRAGILE', 'HANDLE WITH CARE', 'KEEP DRY']),
    design('thanks', 'Thank-you insert', 'thanks', 'Your shop name',
           ['Thank you!', 'Your order means a lot.', 'We hope you enjoy it.', '']),
]


def defaults(item):
    return dict(title=item['name'], subtitle=item['subtitle'],
                rows='\n'.join(item['rows']), qr='')


def render_template(item, values, width, height):
    """Create original artwork at 4x6, then fit proportionally to selected stock."""
    doc = fitz.open()
    try:
        page = doc.new_page(width=288, height=432)
        def text(rect, value, size=10, bold=False, align='left'):
            escaped = html.escape(str(value)).replace('\n', '<br>')
            spare, _ = page.insert_htmlbox(fitz.Rect(rect), '<div>'+escaped+'</div>',
                css=f'* {{font-family: sans-serif; font-size:{size}pt; line-height:1.15;'
                    f'font-weight:{"bold" if bold else "normal"}; text-align:{align}; margin:0; padding:0;}}',
                scale_low=1)
            if spare < 0:
                raise ValueError('Some text is too long for this design. Shorten the title or row text.')

        text((16, 13, 272, 57), values['title'], 17, True)
        text((16, 60, 272, 90), values['subtitle'], 9)
        page.draw_line((16, 94), (272, 94), width=1.3)
        rows = values['rows'].split('\n')
        kind = item['kind']
        limit = {'check':12, 'week':7, 'habits':7, 'stock':11, 'fields':6,
                 'handling':4, 'thanks':5}[kind]
        if len(rows) > limit:
            raise ValueError(f'This design fits up to {limit} rows. Remove extra rows before printing.')
        if kind == 'check':
            for i, row in enumerate(rows):
                y = 108 + i * 24
                page.draw_rect(fitz.Rect(18, y+3, 28, y+13), width=.8)
                text((36, y, 270, y+19), row, 10)
                page.draw_line((36, y+21), (270, y+21), color=(.55,)*3, width=.4)
        elif kind == 'week':
            for i, row in enumerate(rows):
                y = 103+i*43
                label, _, note = row.partition('|')
                text((18,y,270,y+17),label,10,True)
                text((18,y+18,270,y+37),note,10)
                page.draw_line((18,y+40),(270,y+40),width=.4)
        elif kind == 'habits':
            for j, day in enumerate('MTWTFSS'):
                text((111+j*23,108,134+j*23,127),day,9,True,'center')
            for i, row in enumerate(rows):
                y=135+i*36
                text((16,y,108,y+32),row,9)
                for j in range(7):
                    page.draw_rect(fitz.Rect(116+j*23,y+4,128+j*23,y+16),width=.6)
        elif kind == 'stock':
            for i, row in enumerate(rows):
                y=105+i*27
                cells=row.split('|')
                if len(cells)>3:
                    raise ValueError('Table rows have three columns separated by |.')
                boundaries=[16,132,202,272]
                for j in range(3):
                    page.draw_rect(fitz.Rect(boundaries[j],y,boundaries[j+1],y+27),width=.5)
                    text((boundaries[j]+4,y+3,boundaries[j+1]-3,y+25),
                         cells[j].strip() if j<len(cells) else '',8,i==0)
        elif kind == 'fields':
            for i,row in enumerate(rows):
                y=106+i*49
                label,_,value=row.partition('|')
                text((18,y,270,y+18),label,10,True)
                text((18,y+19,270,y+39),value,10)
                page.draw_line((18,y+43),(270,y+43),width=.6)
        elif kind == 'handling':
            for i,row in enumerate(rows):
                y=111+i*70
                page.draw_rect(fitz.Rect(17,y,271,y+62),width=2)
                text((24,y+8,264,y+57),row,20,True,'center')
        elif kind == 'thanks':
            for i,row in enumerate(rows):
                y=111+i*29
                text((18,y,270,y+27),row,16 if i==0 else 11,i==0,'center')
            if values.get('qr','').strip():
                value=values['qr'].strip()
                if len(value)>300:
                    raise ValueError('Keep the QR code value to 300 characters or fewer.')
                image=qrcode.make(value)
                data=io.BytesIO();image.save(data,format='PNG')
                page.insert_image(fitz.Rect(86,277,202,393),stream=data.getvalue())
        result=make_label(doc,0,page.rect,0,width,height)
        return result
    finally:
        doc.close()


class TemplateLibrary:
    """Each import gets a random local name; original paths are never retained."""
    def __init__(self, folder):
        self.folder=Path(folder)
        self.folder.mkdir(parents=True,exist_ok=True)

    def items(self):
        items=[]
        for path in self.folder.glob('*.json'):
            try:
                uuid.UUID(path.stem)
                row=json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(row.get('name'),str) or not (self.folder/(path.stem+'.pdf')).is_file():
                    continue
                items.append(dict(id=path.stem,name=row['name'][:100],custom=True))
            except (ValueError,TypeError,AttributeError,OSError):
                continue
        return sorted(items,key=lambda row:row['name'].casefold())

    def path(self, identifier):
        return self.folder/(str(uuid.UUID(identifier))+'.pdf')

    def add(self, path):
        path=Path(path)
        if path.stat().st_size>50*1024*1024:
            raise ValueError('Choose a template smaller than 50 MB.')
        identifier=str(uuid.uuid4())
        destination=self.path(identifier)
        try:
            with open_document(path) as source, fitz.open() as clean:
                if not 1<=len(source)<=50:
                    raise ValueError('Templates must contain between 1 and 50 pages.')
                source.bake(annots=True,widgets=True)
                for source_page in source:
                    if source_page.rotation:
                        source_page.remove_rotation()
                    # Copy printable artwork only, without links, scripts or attachments.
                    target=clean.new_page(width=source_page.rect.width,height=source_page.rect.height)
                    target.draw_rect(target.rect,color=None,fill=(1,1,1))
                    if source_page.get_contents():
                        target.show_pdf_page(target.rect,source,source_page.number)
                clean.save(destination,garbage=4,deflate=True)
            row=dict(id=identifier,name=path.stem[:100],custom=True)
            self.folder.joinpath(identifier+'.json').write_text(json.dumps({'name':row['name']}),encoding='utf-8')
            return row
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def remove(self, identifier):
        path=self.path(identifier)
        path.unlink(missing_ok=True)
        path.with_suffix('.json').unlink(missing_ok=True)
