import 'package:flutter/material.dart';

import '../theme/theme.dart';

class MpSectionLabel extends StatelessWidget {
  const MpSectionLabel(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      header: true,
      child: Text(
        text,
        style: context.mpText.label.copyWith(color: context.mpColors.textMuted),
      ),
    );
  }
}
