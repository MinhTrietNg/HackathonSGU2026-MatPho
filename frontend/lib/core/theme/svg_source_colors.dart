import 'package:flutter/painting.dart';

import 'mp_colors.dart';

abstract final class SvgSourceColors {
  static const iconOutline = Color(0xFFF2F4F6);

  static const iconAccent = Color(0xFFF5B21E);

  static Color? illustration(
    MpColors c,
    Color source, {
    required bool groundShadow,
  }) {
    return switch (source.toARGB32() & 0xFFFFFF) {
      0x142030 => c.illBlob,
      0x080D13 => groundShadow ? c.illShadow : c.illInk,
      0x34495F => c.illLineStrong,
      0xF2F4F6 => c.illWhite,
      0xA5B1BE => c.illLight,
      0x56697D => c.illMid,
      0x22344A => c.illLine,
      0x1B2A3B => c.illRaised,
      0x0E1620 => c.illSurface,
      0xFF9A4D => c.illHot,
      0x000000 => c.illShade,
      0xF5B21E => c.brandAccent,
      0xFF4A36 => c.statusFire,
      0xFF8A3D => c.statusWarn,
      0x43D18F => c.statusOk,
      _ => null,
    };
  }

  static bool isIllustrationBlob(Color source) =>
      (source.toARGB32() & 0xFFFFFF) == 0x142030;

  static String hex(Color color) =>
      '#${(color.toARGB32() & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}'
          .toUpperCase();
}
