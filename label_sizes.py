"""Named label stock sizes, stored per Windows user."""
import json
import math
import uuid

PRESETS = [
    {'id':'4x6','name':'4 × 6 in · Shipping','width':101.6,'height':152.4},
    {'id':'100x150','name':'100 × 150 mm · Shipping','width':100.,'height':150.},
    {'id':'a6','name':'A6 · 105 × 148 mm','width':105.,'height':148.},
    {'id':'4x4','name':'4 × 4 in · Square','width':101.6,'height':101.6},
    {'id':'4x2','name':'4 × 2 in · Address','width':101.6,'height':50.8},
    {'id':'4x8','name':'4 × 8 in · Long shipping','width':101.6,'height':203.2},
    {'id':'62x100','name':'62 × 100 mm · Brother shipping','width':62.,'height':100.},
    {'id':'62x29','name':'62 × 29 mm · Brother address','width':62.,'height':29.},
]

def validate_size(name,width,height):
    name=str(name).strip()
    width,height=round(float(width),3),round(float(height),3)
    if not name or len(name)>60:
        raise ValueError('Enter a name between 1 and 60 characters.')
    if not all(math.isfinite(v) and 10<=v<=1000 for v in (width,height)):
        raise ValueError('Width and height must each be between 10 and 1000 mm.')
    return name,round(width,3),round(height,3)

class SizeStore:
    def __init__(self,settings):
        self.settings=settings
        self.custom=[]
        try:
            rows=json.loads(settings.value('custom_sizes','[]'))
            for row in rows:
                name,w,h=validate_size(row['name'],row['width'],row['height'])
                if isinstance(row.get('id'),str) and row['id'].startswith('custom-'):
                    self.custom.append(dict(id=row['id'],name=name,width=w,height=h,custom=True))
        except (ValueError,TypeError,KeyError):
            self.custom=[]

    @property
    def sizes(self):
        return PRESETS+self.custom

    def save(self):
        self.settings.setValue('custom_sizes',json.dumps(self.custom))
        self.settings.sync()

    def add(self,name,width,height):
        name,width,height=validate_size(name,width,height)
        for row in self.sizes:
            if abs(row['width']-width)<.01 and abs(row['height']-height)<.01:
                return row
        if any(row['name'].casefold()==name.casefold() for row in self.sizes):
            raise ValueError('That name is already used. Choose a different name.')
        row=dict(id='custom-'+str(uuid.uuid4()),name=name,width=width,height=height,custom=True)
        self.custom.append(row)
        self.save()
        return row

    def remove(self,identifier):
        self.custom=[row for row in self.custom if row['id']!=identifier]
        self.save()

def dimensions_text(size):
    return f"{size['width']:g} × {size['height']:g} mm"
