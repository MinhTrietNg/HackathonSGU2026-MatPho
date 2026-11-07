import 'package:flutter/material.dart';

import 'app_theme.dart';

class MpDarkIsland extends StatelessWidget {
  const MpDarkIsland({super.key, required this.child});

  final Widget child;

  static final _dark = AppTheme.dark();

  @override
  Widget build(BuildContext context) => Theme(data: _dark, child: child);
}
