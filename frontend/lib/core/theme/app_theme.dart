import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'mp_colors.dart';
import 'mp_typography.dart';

abstract final class AppTheme {
  static ThemeData dark() => _build(Brightness.dark, MpColors.dark);

  static ThemeData light() => _build(Brightness.light, MpColors.light);

  static SystemUiOverlayStyle systemOverlayStyle(ThemeData theme) =>
      theme.appBarTheme.systemOverlayStyle!;

  static ThemeData _build(Brightness brightness, MpColors c) {
    const t = MpTypography.regular;
    final scheme = ColorScheme(
      brightness: brightness,
      primary: c.brandAccent,
      onPrimary: c.brandOnAccent,
      primaryContainer: c.brandAccentSoft,
      onPrimaryContainer: c.brandAccentFg,
      secondary: c.brandAccent,
      onSecondary: c.brandOnAccent,
      error: c.statusFire,
      onError: c.onStatusFromLight,
      errorContainer: c.statusFireSoft,
      onErrorContainer: c.statusFire,
      surface: c.bgSurface,
      onSurface: c.textPrimary,
      onSurfaceVariant: c.textSecondary,
      surfaceContainerLowest: c.bgBase,
      surfaceContainerLow: c.bgSurface,
      surfaceContainer: c.bgCard,
      surfaceContainerHigh: c.bgRaised,
      surfaceContainerHighest: c.bgRaised,
      outline: c.lineStrong,
      outlineVariant: c.lineSubtle,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: c.bgBase,
      canvasColor: c.bgBase,
      dividerColor: c.lineSubtle,
      appBarTheme: AppBarTheme(
        systemOverlayStyle: SystemUiOverlayStyle(
          statusBarColor: Colors.transparent,
          statusBarIconBrightness: brightness == Brightness.dark
              ? Brightness.light
              : Brightness.dark,
          statusBarBrightness: brightness,
        ),
      ),
      fontFamily: MpFonts.sans,
      textTheme: TextTheme(
        displaySmall: t.display,
        titleLarge: t.title,
        titleMedium: t.headline,
        bodyLarge: t.body,
        bodyMedium: t.body,
        bodySmall: t.caption,
        labelLarge: t.label,
      ).apply(bodyColor: c.textPrimary, displayColor: c.textPrimary),
      extensions: <ThemeExtension<dynamic>>[c, t],
    );
  }
}
