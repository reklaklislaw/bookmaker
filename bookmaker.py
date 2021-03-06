#!/usr/bin/env python3

""" Commandline entry point
"""

import sys, argparse
import logging

from util import Util
from environment import Environment; Environment('shell')
from processing import ProcessHandling

def main(args):
    try:
        books = Environment.get_books(args.root_dir, args, stage='process')
    except Exception as e:
        Util.bail(str(e))

    P = ProcessHandling()
    queue = P.new_queue()

    for book in books:
        queue.add(book, cls='FeatureDetection', mth='pipeline')
             
        if args.derive_all or args.derive:
            if args.derive:
                formats = args.derive
            else:
                formats = ('djvu', 'pdf', 'epub', 'text')
                
            if book.settings['respawn']:
                queue.add(book, cls='Crop', mth='cropper_pipeline', 
                          kwargs={'crop': 'standardCrop'})

                queue.add(book, cls='OCR', mth='tesseract_hocr_pipeline',
                          kwargs={'lang': args.language})
                
            if 'djvu' in formats:
                queue.add(book, cls='Djvu', mth='make_djvu_with_c44')
                                              
            if 'pdf' in formats:
                queue.add(book, cls='PDF', mth='make_pdf_with_hocr2pdf')
                              
            if 'epub' in formats:
                queue.add(book, cls='EPUB', mth='make_epub')
                                              
            if 'text' in formats:
                queue.add(book, cls='PlainText', mth='make_full_plain_text')
        queue.drain('sync')



if __name__ == "__main__":
    parser = argparse.ArgumentParser('./bookmaker')
    argu = parser.add_argument_group('Required')
    argu.add_argument('--root-dir', nargs='*', required=True, 
                      help='A single item or a directory of items')

    settings = parser.add_argument_group('Settings')
    settings.add_argument('--save-settings', action='store_true', 
                          help='Saves arguments to settings.yaml')

    proc = parser.add_argument_group('Processing')
    proc.add_argument('--respawn', action='store_true', 
                      help='Files/Data will be re-created (default)')
    proc.add_argument('--no-respawn', action='store_true', 
                      help='Files/Data will be not be re-created')

    ocr = parser.add_argument_group('OCR')
    ocr.add_argument('--language', nargs='?', default='English')

    derive = parser.add_argument_group('Derivation')
    derive.add_argument('--active-crop', nargs='?', default='standardCrop')
    derive.add_argument('--derive', nargs='+', 
                        help='Formats: djvu, pdf, epub, text')
    derive.add_argument('--derive-all', action='store_true', 
                        help='Derive all formats')

    debug = parser.add_argument_group('Debug')
    debug.add_argument('--make-cornered-scaled', 
                       action='store_true', default=None)
    debug.add_argument('--draw-clusters', 
                       action='store_true', default=None)
    debug.add_argument('--draw-removed-clusters', 
                       action='store_true', default=None)
    debug.add_argument('--draw-invalid-clusters', 
                       action='store_true', default=None)
    debug.add_argument('--draw-content-dimensions', 
                       action='store_true', default=None)
    debug.add_argument('--draw-page-number-candidates', 
                       action='store_true', default=None)
    debug.add_argument('--draw-noise', action='store_true')

    if len(sys.argv)<2:
        parser.print_help()
        sys.exit(0);
    else:
        args = parser.parse_args()
        main(args)
