import 'package:flutter/material.dart';

@immutable
class MpColors extends ThemeExtension<MpColors> {
  const MpColors({
    required this.bgBase,
    required this.bgSurface,
    required this.bgCard,
    required this.bgRaised,
    required this.lineSubtle,
    required this.lineStrong,
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.brandAccent,
    required this.brandAccentDeep,
    required this.brandAccentSoft,
    required this.brandOnAccent,
    required this.brandAccentFg,
    required this.brandGold,
    required this.statusFire,
    required this.statusFireSoft,
    required this.statusWarn,
    required this.statusWarnSoft,
    required this.statusOk,
    required this.statusOkSoft,
    required this.onStatusFromLight,
    required this.onStatusFromDark,
    required this.actionResolveBg,
    required this.actionResolveLine,
    required this.actionResolveIcon,
    required this.actionResolveFg,
    required this.actionReportBg,
    required this.actionReportLine,
    required this.actionReportFg,
    required this.buttonEdgePrimary,
    required this.buttonEdgeSecondary,
    required this.buttonFaceSecondary,
    required this.buttonEdgeDanger,
    required this.buttonEdgeAmber,
    required this.buttonEdgeReport,
    required this.buttonEdgeResolve,
    required this.alertGlow,
    required this.illBlob,
    required this.illShadow,
    required this.illLineStrong,
    required this.illWhite,
    required this.illLight,
    required this.illInk,
    required this.illMid,
    required this.illLine,
    required this.illRaised,
    required this.illSurface,
    required this.illHot,
    required this.illShade,
    required this.bannerShadow,
  });

  final Color bgBase;

  final Color bgSurface;

  final Color bgCard;

  final Color bgRaised;

  final Color lineSubtle;

  final Color lineStrong;

  final Color textPrimary;

  final Color textSecondary;

  final Color textMuted;

  final Color brandAccent;

  final Color brandAccentDeep;

  final Color brandAccentSoft;

  final Color brandOnAccent;

  final Color brandAccentFg;

  final Color brandGold;

  final Color statusFire;

  final Color statusFireSoft;

  final Color statusWarn;

  final Color statusWarnSoft;

  final Color statusOk;

  final Color statusOkSoft;

  final Color onStatusFromLight;

  final Color onStatusFromDark;

  final Color actionResolveBg;

  final Color actionResolveLine;

  final Color actionResolveIcon;

  final Color actionResolveFg;

  final Color actionReportBg;

  final Color actionReportLine;

  final Color actionReportFg;

  final Color buttonEdgePrimary;

  final Color buttonEdgeSecondary;

  final Color buttonFaceSecondary;

  final Color buttonEdgeDanger;

  final Color buttonEdgeAmber;

  final Color buttonEdgeReport;

  final Color buttonEdgeResolve;

  final Color alertGlow;

  final Color illBlob;

  final Color illShadow;

  final Color illLineStrong;

  final Color illWhite;

  final Color illLight;

  final Color illInk;

  final Color illMid;

  final Color illLine;

  final Color illRaised;

  final Color illSurface;

  final Color illHot;

  final Color illShade;

  final Color bannerShadow;

  static const dark = MpColors(
    bgBase: Color(0xFF080D13),
    bgSurface: Color(0xFF0E1620),
    bgCard: Color(0xFF142030),
    bgRaised: Color(0xFF1B2A3B),
    lineSubtle: Color(0xFF22344A),
    lineStrong: Color(0xFF34495F),
    textPrimary: Color(0xFFF2F4F6),
    textSecondary: Color(0xFFA5B1BE),
    textMuted: Color(0xFF6E7C8B),
    brandAccent: Color(0xFFF5B21E),
    brandAccentDeep: Color(0xFFC98A0C),
    brandAccentSoft: Color(0xFF33270C),
    brandOnAccent: Color(0xFF1A1203),
    brandAccentFg: Color(0xFFF5B21E),
    brandGold: Color(0xFFF5B21E),
    statusFire: Color(0xFFFF4A36),
    statusFireSoft: Color(0xFF3A1A1C),
    statusWarn: Color(0xFFFF8A3D),
    statusWarnSoft: Color(0xFF3A2214),
    statusOk: Color(0xFF43D18F),
    statusOkSoft: Color(0xFF123A2B),
    onStatusFromLight: Color(0xFFF2F4F6),
    onStatusFromDark: Color(0xFF1A1203),
    actionResolveBg: Color(0xFF15803D),
    actionResolveLine: Color(0xFF15803D),
    actionResolveIcon: Color(0xFFFFFFFF),
    actionResolveFg: Color(0xFFFFFFFF),
    actionReportBg: Color(0xFFB97A00),
    actionReportLine: Color(0xFFB97A00),
    actionReportFg: Color(0xFFFFFFFF),
    buttonEdgePrimary: Color(0xFFB98209),
    buttonEdgeSecondary: Color(0xFF0A0F15),
    buttonFaceSecondary: Color(0xFF222B36),
    buttonEdgeDanger: Color(0xFFB8301F),
    buttonEdgeAmber: Color(0xFFC25E1C),
    buttonEdgeReport: Color(0xFF7F5400),
    buttonEdgeResolve: Color(0xFF0E5A2B),
    alertGlow: Color(0xFFFF4A36),
    illBlob: Color(0xFF142030),
    illShadow: Color(0xFF080D13),
    illLineStrong: Color(0xFF34495F),
    illWhite: Color(0xFFF2F4F6),
    illLight: Color(0xFFA5B1BE),
    illInk: Color(0xFF080D13),
    illMid: Color(0xFF56697D),
    illLine: Color(0xFF22344A),
    illRaised: Color(0xFF1B2A3B),
    illSurface: Color(0xFF0E1620),
    illHot: Color(0xFFFF9A4D),
    illShade: Color(0xFF000000),
    bannerShadow: Color(0x2E000000),
  );

  static const light = MpColors(
    bgBase: Color(0xFFF0F2F6),
    bgSurface: Color(0xFFFFFFFF),
    bgCard: Color(0xFFFFFFFF),
    bgRaised: Color(0xFFE8ECF1),
    lineSubtle: Color(0xFFE1E6EC),
    lineStrong: Color(0xFFC4CDD7),
    textPrimary: Color(0xFF0E1620),
    textSecondary: Color(0xFF475565),
    textMuted: Color(0xFF5F6B79),
    brandAccent: Color(0xFFF5B21E),
    brandAccentDeep: Color(0xFFC98A0C),
    brandAccentSoft: Color(0xFFFFF3D3),
    brandOnAccent: Color(0xFF1A1203),
    brandAccentFg: Color(0xFF8F5F00),
    brandGold: Color(0xFFF5B21E),
    statusFire: Color(0xFFC81E2B),
    statusFireSoft: Color(0xFFFEE7E9),
    statusWarn: Color(0xFFC2410C),
    statusWarnSoft: Color(0xFFFFEDD5),
    statusOk: Color(0xFF0F7B4A),
    statusOkSoft: Color(0xFFE5F5EC),
    onStatusFromLight: Color(0xFFFFFFFF),
    onStatusFromDark: Color(0xFF1A1203),
    actionResolveBg: Color(0xFF0F7B4A),
    actionResolveLine: Color(0xFF0F7B4A),
    actionResolveIcon: Color(0xFFFFFFFF),
    actionResolveFg: Color(0xFFFFFFFF),
    actionReportBg: Color(0xFFA16207),
    actionReportLine: Color(0xFFA16207),
    actionReportFg: Color(0xFFFFFFFF),
    buttonEdgePrimary: Color(0xFFC48C0C),
    buttonEdgeSecondary: Color(0xFFC4CDD7),
    buttonFaceSecondary: Color(0xFFFFFFFF),
    buttonEdgeDanger: Color(0xFF8E1220),
    buttonEdgeAmber: Color(0xFFC25E1C),
    buttonEdgeReport: Color(0xFF6E4304),
    buttonEdgeResolve: Color(0xFF0A5533),
    alertGlow: Color(0x00C92A1E),
    illBlob: Color(0xFFE6ECF2),
    illShadow: Color(0xFFD4DCE5),
    illLineStrong: Color(0xFF9FAEBE),
    illWhite: Color(0xFFFFFFFF),
    illLight: Color(0xFF5D6B7C),
    illInk: Color(0xFF26334A),
    illMid: Color(0xFF7F8E9F),
    illLine: Color(0xFFC2CDD9),
    illRaised: Color(0xFFD3DCE6),
    illSurface: Color(0xFFFFFFFF),
    illHot: Color(0xFFFF9A4D),
    illShade: Color(0xFF000000),
    bannerShadow: Color(0x240D141F),
  );

  @override
  MpColors copyWith({
    Color? bgBase,
    Color? bgSurface,
    Color? bgCard,
    Color? bgRaised,
    Color? lineSubtle,
    Color? lineStrong,
    Color? textPrimary,
    Color? textSecondary,
    Color? textMuted,
    Color? brandAccent,
    Color? brandAccentDeep,
    Color? brandAccentSoft,
    Color? brandOnAccent,
    Color? brandAccentFg,
    Color? brandGold,
    Color? statusFire,
    Color? statusFireSoft,
    Color? statusWarn,
    Color? statusWarnSoft,
    Color? statusOk,
    Color? statusOkSoft,
    Color? onStatusFromLight,
    Color? onStatusFromDark,
    Color? actionResolveBg,
    Color? actionResolveLine,
    Color? actionResolveIcon,
    Color? actionResolveFg,
    Color? actionReportBg,
    Color? actionReportLine,
    Color? actionReportFg,
    Color? buttonEdgePrimary,
    Color? buttonEdgeSecondary,
    Color? buttonFaceSecondary,
    Color? buttonEdgeDanger,
    Color? buttonEdgeAmber,
    Color? buttonEdgeReport,
    Color? buttonEdgeResolve,
    Color? alertGlow,
    Color? illBlob,
    Color? illShadow,
    Color? illLineStrong,
    Color? illWhite,
    Color? illLight,
    Color? illInk,
    Color? illMid,
    Color? illLine,
    Color? illRaised,
    Color? illSurface,
    Color? illHot,
    Color? illShade,
    Color? bannerShadow,
  }) {
    return MpColors(
      bgBase: bgBase ?? this.bgBase,
      bgSurface: bgSurface ?? this.bgSurface,
      bgCard: bgCard ?? this.bgCard,
      bgRaised: bgRaised ?? this.bgRaised,
      lineSubtle: lineSubtle ?? this.lineSubtle,
      lineStrong: lineStrong ?? this.lineStrong,
      textPrimary: textPrimary ?? this.textPrimary,
      textSecondary: textSecondary ?? this.textSecondary,
      textMuted: textMuted ?? this.textMuted,
      brandAccent: brandAccent ?? this.brandAccent,
      brandAccentDeep: brandAccentDeep ?? this.brandAccentDeep,
      brandAccentSoft: brandAccentSoft ?? this.brandAccentSoft,
      brandOnAccent: brandOnAccent ?? this.brandOnAccent,
      brandAccentFg: brandAccentFg ?? this.brandAccentFg,
      brandGold: brandGold ?? this.brandGold,
      statusFire: statusFire ?? this.statusFire,
      statusFireSoft: statusFireSoft ?? this.statusFireSoft,
      statusWarn: statusWarn ?? this.statusWarn,
      statusWarnSoft: statusWarnSoft ?? this.statusWarnSoft,
      statusOk: statusOk ?? this.statusOk,
      statusOkSoft: statusOkSoft ?? this.statusOkSoft,
      onStatusFromLight: onStatusFromLight ?? this.onStatusFromLight,
      onStatusFromDark: onStatusFromDark ?? this.onStatusFromDark,
      actionResolveBg: actionResolveBg ?? this.actionResolveBg,
      actionResolveLine: actionResolveLine ?? this.actionResolveLine,
      actionResolveIcon: actionResolveIcon ?? this.actionResolveIcon,
      actionResolveFg: actionResolveFg ?? this.actionResolveFg,
      actionReportBg: actionReportBg ?? this.actionReportBg,
      actionReportLine: actionReportLine ?? this.actionReportLine,
      actionReportFg: actionReportFg ?? this.actionReportFg,
      buttonEdgePrimary: buttonEdgePrimary ?? this.buttonEdgePrimary,
      buttonEdgeSecondary: buttonEdgeSecondary ?? this.buttonEdgeSecondary,
      buttonFaceSecondary: buttonFaceSecondary ?? this.buttonFaceSecondary,
      buttonEdgeDanger: buttonEdgeDanger ?? this.buttonEdgeDanger,
      buttonEdgeAmber: buttonEdgeAmber ?? this.buttonEdgeAmber,
      buttonEdgeReport: buttonEdgeReport ?? this.buttonEdgeReport,
      buttonEdgeResolve: buttonEdgeResolve ?? this.buttonEdgeResolve,
      alertGlow: alertGlow ?? this.alertGlow,
      illBlob: illBlob ?? this.illBlob,
      illShadow: illShadow ?? this.illShadow,
      illLineStrong: illLineStrong ?? this.illLineStrong,
      illWhite: illWhite ?? this.illWhite,
      illLight: illLight ?? this.illLight,
      illInk: illInk ?? this.illInk,
      illMid: illMid ?? this.illMid,
      illLine: illLine ?? this.illLine,
      illRaised: illRaised ?? this.illRaised,
      illSurface: illSurface ?? this.illSurface,
      illHot: illHot ?? this.illHot,
      illShade: illShade ?? this.illShade,
      bannerShadow: bannerShadow ?? this.bannerShadow,
    );
  }

  @override
  MpColors lerp(MpColors? other, double t) {
    if (other == null) return this;
    return MpColors(
      bgBase: Color.lerp(bgBase, other.bgBase, t)!,
      bgSurface: Color.lerp(bgSurface, other.bgSurface, t)!,
      bgCard: Color.lerp(bgCard, other.bgCard, t)!,
      bgRaised: Color.lerp(bgRaised, other.bgRaised, t)!,
      lineSubtle: Color.lerp(lineSubtle, other.lineSubtle, t)!,
      lineStrong: Color.lerp(lineStrong, other.lineStrong, t)!,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      textMuted: Color.lerp(textMuted, other.textMuted, t)!,
      brandAccent: Color.lerp(brandAccent, other.brandAccent, t)!,
      brandAccentDeep: Color.lerp(brandAccentDeep, other.brandAccentDeep, t)!,
      brandAccentSoft: Color.lerp(brandAccentSoft, other.brandAccentSoft, t)!,
      brandOnAccent: Color.lerp(brandOnAccent, other.brandOnAccent, t)!,
      brandAccentFg: Color.lerp(brandAccentFg, other.brandAccentFg, t)!,
      brandGold: Color.lerp(brandGold, other.brandGold, t)!,
      statusFire: Color.lerp(statusFire, other.statusFire, t)!,
      statusFireSoft: Color.lerp(statusFireSoft, other.statusFireSoft, t)!,
      statusWarn: Color.lerp(statusWarn, other.statusWarn, t)!,
      statusWarnSoft: Color.lerp(statusWarnSoft, other.statusWarnSoft, t)!,
      statusOk: Color.lerp(statusOk, other.statusOk, t)!,
      statusOkSoft: Color.lerp(statusOkSoft, other.statusOkSoft, t)!,
      onStatusFromLight: Color.lerp(
        onStatusFromLight,
        other.onStatusFromLight,
        t,
      )!,
      onStatusFromDark: Color.lerp(
        onStatusFromDark,
        other.onStatusFromDark,
        t,
      )!,
      actionResolveBg: Color.lerp(actionResolveBg, other.actionResolveBg, t)!,
      actionResolveLine: Color.lerp(
        actionResolveLine,
        other.actionResolveLine,
        t,
      )!,
      actionResolveIcon: Color.lerp(
        actionResolveIcon,
        other.actionResolveIcon,
        t,
      )!,
      actionResolveFg: Color.lerp(actionResolveFg, other.actionResolveFg, t)!,
      actionReportBg: Color.lerp(actionReportBg, other.actionReportBg, t)!,
      actionReportLine: Color.lerp(
        actionReportLine,
        other.actionReportLine,
        t,
      )!,
      actionReportFg: Color.lerp(actionReportFg, other.actionReportFg, t)!,
      buttonEdgePrimary: Color.lerp(
        buttonEdgePrimary,
        other.buttonEdgePrimary,
        t,
      )!,
      buttonEdgeSecondary: Color.lerp(
        buttonEdgeSecondary,
        other.buttonEdgeSecondary,
        t,
      )!,
      buttonFaceSecondary: Color.lerp(
        buttonFaceSecondary,
        other.buttonFaceSecondary,
        t,
      )!,
      buttonEdgeDanger: Color.lerp(
        buttonEdgeDanger,
        other.buttonEdgeDanger,
        t,
      )!,
      buttonEdgeAmber: Color.lerp(buttonEdgeAmber, other.buttonEdgeAmber, t)!,
      buttonEdgeReport: Color.lerp(
        buttonEdgeReport,
        other.buttonEdgeReport,
        t,
      )!,
      buttonEdgeResolve: Color.lerp(
        buttonEdgeResolve,
        other.buttonEdgeResolve,
        t,
      )!,
      alertGlow: Color.lerp(alertGlow, other.alertGlow, t)!,
      illBlob: Color.lerp(illBlob, other.illBlob, t)!,
      illShadow: Color.lerp(illShadow, other.illShadow, t)!,
      illLineStrong: Color.lerp(illLineStrong, other.illLineStrong, t)!,
      illWhite: Color.lerp(illWhite, other.illWhite, t)!,
      illLight: Color.lerp(illLight, other.illLight, t)!,
      illInk: Color.lerp(illInk, other.illInk, t)!,
      illMid: Color.lerp(illMid, other.illMid, t)!,
      illLine: Color.lerp(illLine, other.illLine, t)!,
      illRaised: Color.lerp(illRaised, other.illRaised, t)!,
      illSurface: Color.lerp(illSurface, other.illSurface, t)!,
      illHot: Color.lerp(illHot, other.illHot, t)!,
      illShade: Color.lerp(illShade, other.illShade, t)!,
      bannerShadow: Color.lerp(bannerShadow, other.bannerShadow, t)!,
    );
  }
}
