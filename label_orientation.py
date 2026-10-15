"""Optional offline orientation check using Windows' installed OCR language."""
import asyncio
import io
import re
from functools import lru_cache
from PIL import Image

WORDS=set('ship shipping shipment sender recipient from to name address street road lane company customer delivery parcel package packages weight reference return service ground next day air mail priority express tracking number barcode postage paid first class royal destination label sample not valid print date order instructions business domestic country contact depot zone total signature leave response'.split())

@lru_cache(maxsize=64)
def image_rotation(png_bytes, fallback):
    try:
        return asyncio.run(_recognize(png_bytes, fallback))
    except Exception:
        # Windows N / stripped installations may have no OCR language installed.
        # Detection and manual rotation remain available without that component.
        return fallback

async def _recognize(png_bytes, fallback):
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
    engine=OcrEngine.try_create_from_language(Language('en-US'))
    if engine is None:
        engine=OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        return fallback
    im=Image.open(io.BytesIO(png_bytes)).convert('RGB')
    im.thumbnail((1400,1400))
    scores=[]
    for angle in (0,90,180,270):
        buffer=io.BytesIO()
        im.rotate(angle,expand=True).save(buffer,format='PNG')
        stream=InMemoryRandomAccessStream()
        writer=DataWriter(stream)
        writer.write_bytes(buffer.getvalue())
        await writer.store_async()
        writer.detach_stream()
        stream.seek(0)
        decoder=await BitmapDecoder.create_async(stream)
        bitmap=await decoder.get_software_bitmap_async()
        result=await engine.recognize_async(bitmap)
        tokens=re.findall('[a-z]+',result.text.lower())
        score=sum(len(word) for word in tokens if word in WORDS)
        scores.append((score,angle))
        bitmap.close()
        stream.close()
    scores.sort(reverse=True)
    # Do not rotate based on a few coincidental recognised letters.
    if scores[0][0]>=12 and scores[0][0]>=scores[1][0]+6:
        return scores[0][1]
    return fallback
