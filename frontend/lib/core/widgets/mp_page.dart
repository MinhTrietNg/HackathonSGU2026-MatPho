import 'package:flutter/material.dart';

import '../theme/theme.dart';
import 'mp_fill_scroll_view.dart';

class MpPage extends StatelessWidget {
  const MpPage({
    super.key,
    this.header,
    this.headerBottom = 16,
    this.gap = 16,
    this.onRefresh,
    required this.children,
  });

  final Widget? header;
  final double headerBottom;
  final double gap;
  final RefreshCallback? onRefresh;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final header = this.header;
    final onRefresh = this.onRefresh;
    final c = context.mpColors;
    Widget body = MpFillScrollView(
      physics: onRefresh == null ? null : const AlwaysScrollableScrollPhysics(),
      child: Padding(
        padding: EdgeInsets.fromLTRB(20, header == null ? 8 : 0, 20, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: gap,
          children: children,
        ),
      ),
    );
    if (onRefresh != null) {
      body = RefreshIndicator(
        onRefresh: onRefresh,
        color: c.brandAccent,
        backgroundColor: c.bgCard,
        child: body,
      );
    }
    return Scaffold(
      backgroundColor: c.bgBase,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (header != null)
              Padding(
                padding: EdgeInsets.fromLTRB(20, 8, 20, headerBottom),
                child: header,
              ),
            Expanded(child: body),
          ],
        ),
      ),
    );
  }
}
