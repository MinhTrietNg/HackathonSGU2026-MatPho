import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/core/theme/theme.dart';
import 'package:mat_pho/core/widgets/mp_brand.dart';
import 'package:mat_pho/core/widgets/mp_duotone_icon.dart';
import 'package:mat_pho/core/widgets/mp_illustration.dart';

void main() {
  group('icons', () {
    test('MpIcons lists every exported glyph', () {
      expect(MpIcons.values.toSet(), _assetsIn('assets/icons'));
      expect(MpIcons.values.toSet().length, MpIcons.values.length);
    });

    test('glyphs use only the two duotone colors', () {
      final duotone = {
        SvgSourceColors.iconOutline.toARGB32(),
        SvgSourceColors.iconAccent.toARGB32(),
      };
      for (final asset in MpIcons.values) {
        final colors = _colorsIn(asset);
        expect(colors, isNotEmpty, reason: asset);
        for (final color in colors) {
          expect(duotone, contains(color), reason: '$asset: $color');
        }
      }
    });
  });

  group('illustrations', () {
    test('MpIllustrations lists every exported artwork', () {
      expect(MpIllustrations.values.toSet(), _assetsIn('assets/illustrations'));
      expect(
        MpIllustrations.values.toSet().length,
        MpIllustrations.values.length,
      );
    });

    const feeds = {
      MpIllustrations.feed,
      MpIllustrations.feedFire,
      MpIllustrations.feedSmoke,
    };

    test('every color has a token', () {
      for (final asset in MpIllustrations.values.where(
        (a) => !feeds.contains(a),
      )) {
        for (final color in _colorsIn(asset)) {
          final token = SvgSourceColors.illustration(
            MpColors.dark,
            Color(color),
            groundShadow: false,
          );
          expect(
            token,
            isNotNull,
            reason: '$asset: ${color.toRadixString(16)}',
          );
          expect(token!.toARGB32(), color, reason: asset);
        }
      }
    });

    test('Vector_2 is the ground shadow (ill/shadow) in every artwork', () {
      for (final asset in MpIllustrations.values.where(
        (a) => !feeds.contains(a),
      )) {
        final svg = File(asset).readAsStringSync();
        expect(
          RegExp(
            r'<path id="Vector_2" opacity="0.7" d="M140 163C187.496 163 226 '
            r'159.866 226 156C226 152.134 187.496 149 140 149C92.5035 149 54 '
            r'152.134 54 156C54 159.866 92.5035 163 140 163Z" fill="#080D13"/>',
          ).hasMatch(svg),
          isTrue,
          reason: asset,
        );
      }
    });

    test('a color without a token fails an assert', () {
      final mapper = MpIllustration.colorMapper(
        MpIllustrations.fire,
        MpColors.dark,
      );
      expect(
        () => mapper.substitute('Vector_9', 'path', 'fill', Color(0xFF123456)),
        throwsA(
          isA<AssertionError>().having(
            (e) => '${e.message}',
            'message',
            allOf(contains(MpIllustrations.fire), contains('123456')),
          ),
        ),
      );
    });

    test('ground shadow maps to ill/shadow, alpha is kept', () {
      final light = MpColors.dark.copyWith(
        illShadow: MpColors.dark.statusOk,
        illInk: MpColors.dark.statusFire,
      );
      final mapper = MpIllustration.colorMapper(MpIllustrations.fire, light);
      final source = Color(0x80080D13);
      expect(
        mapper.substitute('Vector_2', 'path', 'fill', source),
        light.illShadow.withValues(alpha: source.a),
      );
      expect(
        mapper.substitute('Vector_7', 'path', 'fill', source),
        light.illInk.withValues(alpha: source.a),
      );
    });
  });

  test('brand assets exist', () {
    expect({
      MpBrand.logoMark,
      MpBrand.appIcon,
      MpBrand.logoLockup,
    }, _assetsIn('assets/brand'));
  });
}

Set<String> _assetsIn(String dir) => {
  for (final f in Directory(dir).listSync())
    if (f.path.endsWith('.svg')) '$dir/${f.uri.pathSegments.last}',
};

Set<int> _colorsIn(String asset) {
  final svg = File(asset).readAsStringSync();
  return {
    for (final m in RegExp(
      r'(?:fill|stroke|stop-color)="([^"]+)"',
    ).allMatches(svg))
      if (m[1] != 'none' && !m[1]!.startsWith('url('))
        switch (m[1]!) {
          'black' => 0xFF000000,
          'white' => 0xFFFFFFFF,
          final hex => 0xFF000000 | int.parse(hex.substring(1), radix: 16),
        },
  };
}
