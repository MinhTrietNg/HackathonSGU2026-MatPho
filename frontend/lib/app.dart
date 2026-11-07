import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/router/app_router.dart';
import 'core/theme/appearance.dart';
import 'core/theme/theme.dart';
import 'features/alert/alert_notifications.dart';

class MatPhoApp extends ConsumerWidget {
  const MatPhoApp({super.key});

  static final scrollBehavior = const MaterialScrollBehavior().copyWith(
    overscroll: false,
  );

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: 'Mắt Phố',
      debugShowCheckedModeBanner: false,
      scrollBehavior: scrollBehavior,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ref.watch(lightAppearanceProvider)
          ? ThemeMode.light
          : ThemeMode.dark,
      locale: const Locale('vi'),
      supportedLocales: const [Locale('vi')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      routerConfig: ref.watch(appRouterProvider),
      builder: (context, child) => AnnotatedRegion<SystemUiOverlayStyle>(
        value: AppTheme.systemOverlayStyle(Theme.of(context)),
        child: AlertNotifications(child: child!),
      ),
    );
  }
}
