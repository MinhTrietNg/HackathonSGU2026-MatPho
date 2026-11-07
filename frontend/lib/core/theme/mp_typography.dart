import 'package:flutter/material.dart';

abstract final class MpFonts {
  static const sans = 'Be Vietnam Pro';
  static const mono = 'IBM Plex Mono';
}

@immutable
class MpTypography extends ThemeExtension<MpTypography> {
  const MpTypography({
    required this.display,
    required this.title,
    required this.headline,
    required this.body,
    required this.caption,
    required this.mono,
    required this.label,
  });

  final TextStyle display;

  final TextStyle title;

  final TextStyle headline;

  final TextStyle body;

  final TextStyle caption;

  final TextStyle mono;

  final TextStyle label;

  static const regular = MpTypography(
    display: TextStyle(
      fontFamily: MpFonts.sans,
      fontSize: 30,
      fontWeight: FontWeight.w700,
      height: 1.25,
      letterSpacing: 0,
      leadingDistribution: TextLeadingDistribution.even,
    ),
    title: TextStyle(
      fontFamily: MpFonts.sans,
      fontSize: 22,
      fontWeight: FontWeight.w700,
      height: 1.3,
      letterSpacing: 0,
      leadingDistribution: TextLeadingDistribution.even,
    ),
    headline: TextStyle(
      fontFamily: MpFonts.sans,
      fontSize: 16,
      fontWeight: FontWeight.w600,
      height: 1.4,
      letterSpacing: 0,
      leadingDistribution: TextLeadingDistribution.even,
    ),
    body: TextStyle(
      fontFamily: MpFonts.sans,
      fontSize: 14,
      fontWeight: FontWeight.w400,
      height: 1.5,
      letterSpacing: 0,
      leadingDistribution: TextLeadingDistribution.even,
    ),
    caption: TextStyle(
      fontFamily: MpFonts.sans,
      fontSize: 12,
      fontWeight: FontWeight.w400,
      height: 1.4,
      letterSpacing: 0,
      leadingDistribution: TextLeadingDistribution.even,
    ),
    mono: TextStyle(
      fontFamily: MpFonts.mono,
      fontSize: 12,
      fontWeight: FontWeight.w500,
      height: 1.4,
      letterSpacing: 0,
      leadingDistribution: TextLeadingDistribution.even,
    ),
    label: TextStyle(
      fontFamily: MpFonts.sans,
      fontSize: 13,
      fontWeight: FontWeight.w700,
      height: 1.3,
      letterSpacing: 0,
      leadingDistribution: TextLeadingDistribution.even,
    ),
  );

  @override
  MpTypography copyWith({
    TextStyle? display,
    TextStyle? title,
    TextStyle? headline,
    TextStyle? body,
    TextStyle? caption,
    TextStyle? mono,
    TextStyle? label,
  }) {
    return MpTypography(
      display: display ?? this.display,
      title: title ?? this.title,
      headline: headline ?? this.headline,
      body: body ?? this.body,
      caption: caption ?? this.caption,
      mono: mono ?? this.mono,
      label: label ?? this.label,
    );
  }

  @override
  MpTypography lerp(MpTypography? other, double t) {
    if (other == null) return this;
    return MpTypography(
      display: TextStyle.lerp(display, other.display, t)!,
      title: TextStyle.lerp(title, other.title, t)!,
      headline: TextStyle.lerp(headline, other.headline, t)!,
      body: TextStyle.lerp(body, other.body, t)!,
      caption: TextStyle.lerp(caption, other.caption, t)!,
      mono: TextStyle.lerp(mono, other.mono, t)!,
      label: TextStyle.lerp(label, other.label, t)!,
    );
  }
}
