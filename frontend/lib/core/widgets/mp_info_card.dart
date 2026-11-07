import 'package:flutter/material.dart';

import '../theme/theme.dart';

typedef MpInfoRow = ({String label, String value, Color? valueColor});

class MpInfoCard extends StatelessWidget {
  const MpInfoCard({super.key, required this.rows});

  final List<MpInfoRow> rows;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final label = t.caption.copyWith(
      fontWeight: FontWeight.w500,
      color: c.textSecondary,
    );
    final value = t.body.copyWith(fontWeight: FontWeight.w700);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        children: [
          for (final (i, row) in rows.indexed)
            MergeSemantics(
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: i == rows.length - 1
                    ? null
                    : BoxDecoration(
                        border: Border(bottom: BorderSide(color: c.lineSubtle)),
                      ),
                child: Row(
                  spacing: 10,
                  children: [
                    Text(row.label, style: label),
                    Expanded(
                      child: Text(
                        row.value,
                        textAlign: TextAlign.right,
                        style: value.copyWith(
                          color: row.valueColor ?? c.textPrimary,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
