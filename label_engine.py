"""Local label extraction. PDF artwork remains vector artwork on export."""
import io
import pymupdf as fitz
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageSequence


def open_document(path):
    if str(path).lower().endswith('.pdf'):
        doc = fitz.open(path)
        if doc.needs_pass:
            doc.close()
            raise ValueError('This PDF is password protected. Save an unlocked copy first.')
        return doc
    doc = fitz.open()
    try:
        with Image.open(path, formats=['PNG', 'JPEG', 'TIFF', 'BMP', 'GIF', 'WEBP']) as source:
            for frame in ImageSequence.Iterator(source):
                im = ImageOps.exif_transpose(frame).convert('RGBA')
                white = Image.new('RGBA', im.size, 'white')
                white.alpha_composite(im)
                data = io.BytesIO()
                white.convert('RGB').save(data, format='PNG')
                page = doc.new_page(width=im.width * .24, height=im.height * .24)
                page.insert_image(page.rect, stream=data.getvalue())
    except Exception:
        doc.close()
        raise ValueError('Open a PDF, PNG, JPEG, TIFF, BMP, GIF or WebP file. For other formats, save or print to PDF first.')
    return doc


def detect_label(page):
    # Bring PDF coordinates and rendered coordinates into the same space.
    # FedEx sheets commonly use /Rotate rather than rotating the artwork.
    if page.rotation:
        page.remove_rotation()
    scale = 1200 / max(page.rect.width, page.rect.height)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False)
    gray = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)
    ink = (gray < 170).astype(np.uint8)
    # A label-sized page is already cropped. Do not mistake a separated barcode
    # for the entire label (notably Evri's spacious 4x6 layout).
    native = (abs(page.rect.width-288) < 16 and abs(page.rect.height-432) < 20) or (abs(page.rect.width-432)<20 and abs(page.rect.height-288)<16)
    if native:
        rect = page.rect
        return rect, _rotation(page, rect), 'Label-sized page retained in full. Check orientation before printing.'
    # Remove long page rules before clustering: cut lines and enclosing guide
    # frames must not connect a shipping label to its receipt or instructions.
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, max(80, pix.width//2)), np.uint8))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((max(100,pix.height//2),1), np.uint8))
    clean = ink & (1-cv2.dilate(horizontal | vertical, np.ones((3,3),np.uint8)))
    _, _, edge_stats, _=cv2.connectedComponentsWithStats(cv2.dilate(clean,np.ones((19,19),np.uint8)))
    for x,y,w,h,_ in edge_stats[1:]:
        if h<36 and w>h*5 and (y<pix.height*.065 or y>pix.height*.96):
            clean[y:y+h,x:x+w]=0
    candidates = []
    for gap in (19,35,55,85,115):
        joined = cv2.dilate(clean, np.ones((gap,gap),np.uint8))
        _, labels, stats, _ = cv2.connectedComponentsWithStats(joined)
        for component,(x,y,w,h,area) in enumerate(stats[1:],1):
            if w < 90 or h < 90:
                continue
            ys,xs=np.where((labels[y:y+h,x:x+w]==component) & clean[y:y+h,x:x+w].astype(bool))
            if not len(xs):
                continue
            x0,y0,x1,y1=x+xs.min(),y+ys.min(),x+xs.max()+1,y+ys.max()+1
            w,h=x1-x0,y1-y0
            aspect=max(w,h)/max(1,min(w,h))
            if aspect>2.3:
                continue
            if aspect<1.15 and min(w,h)<220:
                continue  # Small square logos and 2D codes are not whole labels.
            density=clean[y0:y1,x0:x1].sum()/(w*h)
            if density<.065:
                continue
            ratio_score=np.exp(-3*abs(np.log(aspect/1.5)))
            score=(w*h)**.55 * density**1.5 * ratio_score
            candidates.append((score,(x0-8,y0-8,x1+8,y1+8)))
    if not candidates:
        return page.rect, 0, 'No clear label found. Drag around the label on the source page.'
    _, box = max(candidates)
    rect = fitz.Rect(*(float(v) / scale for v in box)) & page.rect
    # An embedded label image is an important boundary signal. Recover sparse
    # address/header areas that connected-component detection can leave behind.
    # Split receipt sheets at whitespace before considering an expansion.
    for info in page.get_image_info():
        bounds=fitz.Rect(info['bbox'])
        if not page.rect.contains(bounds) or bounds.width<150 or bounds.height<150 or bounds.get_area()>page.rect.get_area()*.75:
            continue
        x0,y0=max(0,int(bounds.x0*scale)),max(0,int(bounds.y0*scale))
        x1,y1=min(pix.width,int(bounds.x1*scale)),min(pix.height,int(bounds.y1*scale))
        region=clean[y0:y1,x0:x1]
        if not region.size:
            continue
        rows=np.count_nonzero(region,axis=1)
        blank=rows<=2
        starts=np.where(np.diff(np.r_[False,blank,False].astype(int))==1)[0]
        ends=np.where(np.diff(np.r_[False,blank,False].astype(int))==-1)[0]
        split_sheet=False
        for start,end in zip(starts,ends):
            if end-start<24:
                continue
            if rect.y1*scale<=y0+end and y0+start>rect.y0*scale:
                if start>20 and end<len(rows)-20:
                    split_sheet=True
            elif rect.y0*scale>=y0+start and y0+end<rect.y1*scale:
                if start>20 and end<len(rows)-20:
                    split_sheet=True
        if split_sheet:
            continue
        image_rect=fitz.Rect(x0/scale,y0/scale,x1/scale,y1/scale)
        overlap=(rect & image_rect).get_area()
        if overlap < image_rect.get_area()*.38 or overlap < rect.get_area()*.65:
            continue
        ys,xs=np.where(ink[y0:y1,x0:x1])
        if len(xs):
            expanded=fitz.Rect((x0+xs.min()-8)/scale,(y0+ys.min()-8)/scale,(x0+xs.max()+9)/scale,(y0+ys.max()+9)/scale)&page.rect
            rect |= expanded
    return rect, _rotation(page, rect), 'Suggested complete label. Check all edges and barcodes before printing.'


def _rotation(page, rect):
    votes = {}
    for block in page.get_text('dict', clip=rect)['blocks']:
        for line in block.get('lines', []):
            direction = tuple(round(v) for v in line['dir'])
            votes[direction] = votes.get(direction, 0) + sum(len(s['text']) for s in line['spans'])
    direction = max(votes, key=votes.get) if votes else (1, 0)
    rotation = {(1, 0): 0, (0, 1): 90, (-1, 0): 180, (0, -1): 270}.get(direction, 0)
    # For image-only landscape crops, choose portrait; the user can correct orientation.
    if not votes and rect.width > rect.height*1.15:
        rotation = 90
    if sum(votes.values())<30:
        from label_orientation import image_rotation
        pix=page.get_pixmap(matrix=fitz.Matrix(2,2),clip=rect,alpha=False)
        rotation=image_rotation(pix.tobytes('png'),rotation)
    return rotation


def make_label(doc, page_number, crop, rotation, width_mm=101.6, height_mm=152.4):
    from label_sizes import validate_size
    _,width_mm,height_mm=validate_size('Output',width_mm,height_mm)
    crop = fitz.Rect(crop) & doc[page_number].rect
    if crop.is_empty or crop.width < 2 or crop.height < 2:
        raise ValueError('Select a larger area around the label.')
    result = fitz.open()
    width,height=width_mm*72/25.4,height_mm*72/25.4
    page = result.new_page(width=width, height=height)
    page.show_pdf_page(fitz.Rect(4, 4, width-4, height-4), doc, page_number, clip=crop, rotate=rotation, keep_proportion=True)
    return result
