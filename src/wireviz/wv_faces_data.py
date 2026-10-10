"""Verified connector face layouts for the vehicle view (wv_faces).

Every cavity id and position below was read off the maker's drawing, wire
(rear, grommet) side, latch up, normalised 0..1 (x right, y down). ``main`` is
the half the drawing shows (DT06/DTM06/DTP06 plug, HD36 pin insert, AMPSEAL
776164 receptacle); ``mate`` is the other half's own wire-side view, checked
against its own drawing. ``match`` patterns pick the half from a part number.
Extracted 2026-10-09; DT06-4S and the HD30 24-29 size pattern spot-checked
by hand against the TE drawings. ``source`` cites the drawing for each.
"""

FACES = {'DT-2': {'match': [('\\bDT06-2S', 'main'), ('\\bDT04-2P', 'mate')],
          'shape': 'rect',
          'aspect': 1.27,
          'housing': '#55585b',
          'main': {'view': 'WIRE (rear, grommet) side, plug half DT06-2S, latch up',
                   'cavities': [('1', 0.336, 0.427, 16), ('2', 0.668, 0.427, 16)]},
          'source': '/Volumes/crucial_ssd/HomeX/Docs/Porsche '
                    '914/evaluation/2026-10-03-forensic-audit/evidence/cat-deutsch/TE_DT06-2S-XXXX_customer_drawing.pdf, '
                    "sheet 1, Figure 1 left end view (leaders 'CAVITY 1' and 'GROMMET'); also "
                    "molded '1 2' marks on side view; mate checked on "
                    'TE_DT04-2P-XXXX_customer_drawing.pdf Figure 1',
          'mate': {'view': 'WIRE side, lock up, DT04-2P',
                   'cavities': [('1', 0.664, 0.427, 16), ('2', 0.332, 0.427, 16)]}},
 'DT-3': {'match': [('\\bDT06-3S', 'main'), ('\\bDT04-3P', 'mate')],
          'shape': 'tri',
          'aspect': 1.1,
          'housing': '#55585b',
          'main': {'view': 'WIRE (rear, grommet) side, plug half DT06-3S, latch up',
                   'cavities': [('A', 0.716, 0.314, 16),
                                ('B', 0.274, 0.314, 16),
                                ('C', 0.495, 0.733, 16)]},
          'source': 'https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocType=Customer+Drawing&DocLang=English&DocNm=DT06-3S-XXXX '
                    '(TE C-DT06-3S-XXXX rev D5, fetched 2026-10-09), sheet 1, Figure 1 and Figure '
                    "2 left end views (leaders 'CAVITY A', 'CAVITY C', 'GROMMET'; molded letters "
                    'A, B, C in Figure 2); mate: '
                    'https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocType=Customer+Drawing&DocLang=English&DocNm=DT04-3P-XXXX '
                    'rev D3',
          'mate': {'view': 'WIRE side, lock up, DT04-3P',
                   'cavities': [('A', 0.284, 0.314, 16),
                                ('B', 0.726, 0.314, 16),
                                ('C', 0.505, 0.733, 16)]}},
 'DT-4': {'match': [('\\bDT06-4S', 'main'), ('\\bDT04-4P', 'mate')],
          'shape': 'rect',
          'aspect': 1.27,
          'housing': '#55585b',
          'main': {'view': 'WIRE (rear, grommet) side, plug half DT06-4S, latch up',
                   'cavities': [('1', 0.734, 0.358, 16),
                                ('2', 0.734, 0.647, 16),
                                ('3', 0.267, 0.647, 16),
                                ('4', 0.27, 0.358, 16)]},
          'source': '/Volumes/crucial_ssd/HomeX/Docs/Porsche '
                    '914/evaluation/2026-10-03-forensic-audit/evidence/cat-deutsch/TE_DT06-4S-XXXX_customer_drawing.pdf, '
                    'sheet 1, Figure 1 and Figure 3 left end views (molded numerals 1-4 beside '
                    "cavities, 'GROMMET' leader); mate checked on "
                    'TE_DT04-4P-XXXX_customer_drawing.pdf',
          'mate': {'view': 'WIRE side, lock up, DT04-4P',
                   'cavities': [('1', 0.266, 0.358, 16),
                                ('2', 0.266, 0.647, 16),
                                ('3', 0.733, 0.647, 16),
                                ('4', 0.73, 0.358, 16)]}},
 'DT-6': {'match': [('\\bDT06-6S', 'main'), ('\\bDT04-6P', 'mate')],
          'shape': 'rect',
          'aspect': 0.99,
          'housing': '#55585b',
          'main': {'view': 'WIRE (rear, grommet) side, plug half DT06-6S, latch up',
                   'cavities': [('1', 0.733, 0.272, 16),
                                ('2', 0.733, 0.496, 16),
                                ('3', 0.733, 0.717, 16),
                                ('4', 0.267, 0.717, 16),
                                ('5', 0.267, 0.496, 16),
                                ('6', 0.267, 0.272, 16)]},
          'source': '/Volumes/crucial_ssd/HomeX/Docs/Porsche '
                    '914/evaluation/2026-10-03-forensic-audit/evidence/cat-deutsch/TE_DT06-6S-XXXX_customer_drawing.pdf, '
                    "sheet 1, Figure 1 and Figure 3 left end views (molded numerals 1-6, 'GROMMET' "
                    'leader); mate checked on TE_DT04-6P-XXXX_customer_drawing.pdf',
          'mate': {'view': 'WIRE side, lock up, DT04-6P',
                   'cavities': [('1', 0.267, 0.272, 16),
                                ('2', 0.267, 0.496, 16),
                                ('3', 0.267, 0.717, 16),
                                ('4', 0.733, 0.717, 16),
                                ('5', 0.733, 0.496, 16),
                                ('6', 0.733, 0.272, 16)]}},
 'DT-8': {'match': [('\\bDT06-08S', 'main'), ('\\bDT04-08P', 'mate')],
          'shape': 'rect',
          'aspect': 0.82,
          'housing': '#55585b',
          'main': {'view': 'WIRE (rear, grommet) side, plug half DT06-08SX (X = A/B/C/D key; key '
                           'affects only the mating face), as drawn on the sheet: portrait, E-seal '
                           'mark at the bottom',
                   'cavities': [('1', 0.719, 0.224, 16),
                                ('2', 0.719, 0.394, 16),
                                ('3', 0.719, 0.606, 16),
                                ('4', 0.719, 0.776, 16),
                                ('5', 0.287, 0.776, 16),
                                ('6', 0.287, 0.606, 16),
                                ('7', 0.287, 0.394, 16),
                                ('8', 0.287, 0.224, 16)]},
          'source': 'https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocType=Customer+Drawing&DocLang=English&DocNm=DT06-08SX-XXXX '
                    '(TE C-DT06-08SX-XXXX rev B5, fetched 2026-10-09; DocNm DT06-08SA-XXXX returns '
                    'HTTP 500), sheet 1, Figure 1 and Figure 2 left end views (molded numerals '
                    '1-8, isometric confirms); mate: '
                    'https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocType=Customer+Drawing&DocLang=English&DocNm=DT04-08PX-XXXX '
                    'rev B3 sheet 1 Figure 1',
          'mate': {'view': 'WIRE side, same portrait frame, DT04-08PA',
                   'cavities': [('1', 0.281, 0.224, 16),
                                ('2', 0.281, 0.394, 16),
                                ('3', 0.281, 0.606, 16),
                                ('4', 0.281, 0.776, 16),
                                ('5', 0.713, 0.776, 16),
                                ('6', 0.713, 0.606, 16),
                                ('7', 0.713, 0.394, 16),
                                ('8', 0.713, 0.224, 16)]}},
 'DTM-3': {'match': [('\\bDTM06-3S', 'main'), ('\\bDTM04-3P', 'mate')],
           'shape': 'rect',
           'aspect': 1.86,
           'housing': '#55585b',
           'main': {'view': 'WIRE (rear, grommet) side, plug half DTM06-3S, latch up',
                    'cavities': [('1', 0.245, 0.41, 20),
                                 ('2', 0.5, 0.41, 20),
                                 ('3', 0.755, 0.41, 20)]},
           'source': 'Numbering: '
                     'https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocType=Customer+Drawing&DocLang=English&DocNm=DTM06-3S-E007 '
                     '(Deutsch envelope drawing DTM06-3S-E007 rev A, 2012, scanned), left end '
                     "view, molded '1' left and '3' right with latch up. Geometry: "
                     'https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocType=Customer+Drawing&DocLang=English&DocNm=DTM06-3S '
                     '(Deutsch envelope DTM06-3S rev A, 2001), left end view (no cavity numbers on '
                     'that sheet). Mate: '
                     'https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocType=Customer+Drawing&DocLang=English&DocNm=DTM04-3P-XXXX '
                     'rev A1',
           'mate': {'view': 'WIRE side, lock up, DTM04-3P',
                    'cavities': [('1', 0.755, 0.41, 20),
                                 ('2', 0.5, 0.41, 20),
                                 ('3', 0.245, 0.41, 20)]}},
 'DTP-2': {'match': [('\\bDTP06-2S', 'main'), ('\\bDTP04-2P', 'mate')],
           'shape': 'rect',
           'aspect': 1.4,
           'housing': '#55585b',
           'main': {'view': 'WIRE (rear, grommet) side, plug half DTP06-2S, latch up',
                    'cavities': [('1', 0.322, 0.478, 12), ('2', 0.683, 0.478, 12)]},
           'source': 'https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocType=Customer+Drawing&DocLang=English&DocNm=DTP06-2S-XXXX '
                     '(TE C-DTP06-2S-XXXX rev A1, fetched 2026-10-09), sheet 1, Figure 1 and 2 '
                     "left end views (molded '1' left, '2' right); mate: "
                     'https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocType=Customer+Drawing&DocLang=English&DocNm=DTP04-2P-XXXX '
                     'rev A',
           'mate': {'view': 'WIRE side, lock up, DTP04-2P',
                    'cavities': [('1', 0.678, 0.478, 12), ('2', 0.317, 0.478, 12)]}},
 'DTP-4': {'match': [('\\bDTP06-4S', 'main'), ('\\bDTP04-4P', 'mate')],
           'shape': 'rect',
           'aspect': 1.14,
           'housing': '#55585b',
           'main': {'view': 'WIRE (rear, grommet) side, plug half DTP06-4S, latch up',
                    'cavities': [('1', 0.731, 0.327, 12),
                                 ('2', 0.729, 0.673, 12),
                                 ('3', 0.267, 0.673, 12),
                                 ('4', 0.271, 0.327, 12)]},
           'source': '/Volumes/crucial_ssd/HomeX/Docs/Porsche '
                     '914/evaluation/2026-10-03-forensic-audit/evidence/cat-deutsch/TE_DTP06-4S-XXXX_customer_drawing.pdf, '
                     'sheet 1, Figure 1, 2 and 3 left end views (molded numerals 1-4); mate: '
                     'https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocType=Customer+Drawing&DocLang=English&DocNm=DTP04-4P-XXXX '
                     'rev A',
           'mate': {'view': 'WIRE side, lock up, DTP04-4P',
                    'cavities': [('1', 0.269, 0.327, 12),
                                 ('2', 0.271, 0.673, 12),
                                 ('3', 0.733, 0.673, 12),
                                 ('4', 0.729, 0.327, 12)]}},
 'HD30-24-29': {'match': [('\\bHD36-24-29P', 'main'), ('\\bHD34-24-29S', 'mate')],
                'shape': 'round',
                'aspect': 1.0,
                'housing': '#2a2a2a',
                'main': {'view': "WIRE (rear, grommet) side of the PIN insert ('PIN' view), as "
                                 'drawn',
                         'cavities': [('1', 0.5, 0.336, 12),
                                      ('2', 0.405, 0.5, 12),
                                      ('3', 0.5, 0.663, 12),
                                      ('4', 0.595, 0.5, 12),
                                      ('5', 0.5, 0.164, 16),
                                      ('6', 0.38, 0.224, 16),
                                      ('7', 0.338, 0.351, 16),
                                      ('8', 0.249, 0.451, 16),
                                      ('9', 0.265, 0.584, 16),
                                      ('10', 0.339, 0.696, 16),
                                      ('11', 0.418, 0.806, 16),
                                      ('12', 0.583, 0.806, 16),
                                      ('13', 0.66, 0.696, 16),
                                      ('14', 0.734, 0.586, 16),
                                      ('15', 0.75, 0.451, 16),
                                      ('16', 0.663, 0.351, 16),
                                      ('17', 0.62, 0.224, 16),
                                      ('18', 0.26, 0.216, 20),
                                      ('19', 0.206, 0.325, 16),
                                      ('20', 0.121, 0.414, 20),
                                      ('21', 0.142, 0.533, 16),
                                      ('22', 0.206, 0.705, 16),
                                      ('23', 0.296, 0.81, 20),
                                      ('24', 0.703, 0.81, 20),
                                      ('25', 0.793, 0.705, 16),
                                      ('26', 0.859, 0.533, 16),
                                      ('27', 0.878, 0.414, 20),
                                      ('28', 0.795, 0.325, 16),
                                      ('29', 0.741, 0.216, 20)]},
                'source': '/Volumes/crucial_ssd/HomeX/Docs/Porsche '
                          '914/evaluation/2026-10-03-forensic-audit/evidence/eng-bulkhead-rtmr/TE-0425-014-2400-revH-HD30-size24-arrangements.pdf '
                          '(same drawing as '
                          'cat-deutsch/TE_0425-014-2400_HD30_size24_arrangements.pdf), sheet 2, '
                          "panel '4 CONTACTS SIZE #12 / 19 CONTACTS SIZE #16 / 6 CONTACTS SIZE #20 "
                          "/ THIS ARRANGEMENT IS FOR 'E' SEAL ONLY', views 'SKT.' and 'PIN'; sheet "
                          "1 note 1 'ALL VIEWS SHOW REAR END (GROMMET) OF CONNECTOR.' Size-20 "
                          'positions: /Volumes/crucial_ssd/HomeX/Docs/Porsche '
                          '914/evaluation/2026-10-03-forensic-audit/evidence/eng-bulkhead-rtmr/TE-114-151014-RevD-HD30-Application-Specification.pdf '
                          "p5 '24-29' pin-arrangement figure and "
                          '/Volumes/crucial_ssd/HomeX/Docs/Porsche '
                          '914/evaluation/2026-10-03-forensic-audit/evidence/buy-harness/TE-DEUTSCH-HD30-HDP20-catalog_2020-11_rs-A700000015401052.pdf '
                          "p9 '24-29' figure Size-20 cavities (18, 20, 23, 24, 27, 29) inferred by "
                          'overlaying TE 114-151014 p5 and the 2020 HD30 catalogue p9; '
                          'insert-to-key clocking not confirmed.',
                'mate': {'view': 'WIRE side, SKT. view as drawn, HD34-24-29SE',
                         'cavities': [('1', 0.5, 0.336, 12),
                                      ('2', 0.595, 0.5, 12),
                                      ('3', 0.5, 0.663, 12),
                                      ('4', 0.405, 0.5, 12),
                                      ('5', 0.5, 0.164, 16),
                                      ('6', 0.62, 0.224, 16),
                                      ('7', 0.662, 0.351, 16),
                                      ('8', 0.751, 0.451, 16),
                                      ('9', 0.735, 0.584, 16),
                                      ('10', 0.661, 0.696, 16),
                                      ('11', 0.582, 0.806, 16),
                                      ('12', 0.417, 0.806, 16),
                                      ('13', 0.34, 0.696, 16),
                                      ('14', 0.266, 0.586, 16),
                                      ('15', 0.25, 0.451, 16),
                                      ('16', 0.337, 0.351, 16),
                                      ('17', 0.38, 0.224, 16),
                                      ('18', 0.74, 0.216, 20),
                                      ('19', 0.794, 0.325, 16),
                                      ('20', 0.879, 0.414, 20),
                                      ('21', 0.858, 0.533, 16),
                                      ('22', 0.794, 0.705, 16),
                                      ('23', 0.704, 0.81, 20),
                                      ('24', 0.297, 0.81, 20),
                                      ('25', 0.207, 0.705, 16),
                                      ('26', 0.141, 0.533, 16),
                                      ('27', 0.122, 0.414, 20),
                                      ('28', 0.205, 0.325, 16),
                                      ('29', 0.259, 0.216, 20)]}},
 'AMPSEAL-35': {'match': [('\\b776164', 'main')],
                'shape': 'rect',
                'aspect': 2.3,
                'housing': '#222222',
                'main': {'view': 'WIRE (rear) side of the 776164 receptacle housing, latch up',
                         'cavities': [('1', 0.157, 0.358, None),
                                      ('2', 0.22, 0.358, None),
                                      ('3', 0.283, 0.358, None),
                                      ('4', 0.346, 0.358, None),
                                      ('5', 0.409, 0.358, None),
                                      ('6', 0.472, 0.358, None),
                                      ('7', 0.534, 0.358, None),
                                      ('8', 0.597, 0.358, None),
                                      ('9', 0.66, 0.358, None),
                                      ('10', 0.723, 0.358, None),
                                      ('11', 0.786, 0.358, None),
                                      ('12', 0.848, 0.358, None),
                                      ('13', 0.187, 0.503, None),
                                      ('14', 0.25, 0.503, None),
                                      ('15', 0.313, 0.503, None),
                                      ('16', 0.376, 0.503, None),
                                      ('17', 0.439, 0.503, None),
                                      ('18', 0.501, 0.503, None),
                                      ('19', 0.564, 0.503, None),
                                      ('20', 0.627, 0.503, None),
                                      ('21', 0.69, 0.503, None),
                                      ('22', 0.753, 0.503, None),
                                      ('23', 0.816, 0.503, None),
                                      ('24', 0.157, 0.649, None),
                                      ('25', 0.22, 0.649, None),
                                      ('26', 0.283, 0.649, None),
                                      ('27', 0.346, 0.649, None),
                                      ('28', 0.408, 0.649, None),
                                      ('29', 0.471, 0.649, None),
                                      ('30', 0.534, 0.649, None),
                                      ('31', 0.596, 0.649, None),
                                      ('32', 0.659, 0.649, None),
                                      ('33', 0.722, 0.649, None),
                                      ('34', 0.785, 0.649, None),
                                      ('35', 0.847, 0.649, None)]},
                'source': '/Volumes/crucial_ssd/HomeX/Docs/Porsche '
                          '914/evaluation/2026-10-03-forensic-audit/evidence/verify/t2-36_te_ampseal_catalog_1654285-2.pdf, '
                          "p11 (catalogue page 29-11, '35 Positions Receptacle Housings', end view "
                          "right of the section view; molded '1' top-left, '12' top-right, '24' "
                          "bottom-left, '35' bottom-right); middle-row order from p18 (29-18, 35 "
                          'Positions Right-Angle PCB Headers, face view labels 1, 12, 13, 23, 24, '
                          '35)'}}
