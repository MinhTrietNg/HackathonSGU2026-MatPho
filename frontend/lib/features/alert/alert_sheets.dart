library;

import 'package:flutter/material.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_chip.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_sheet.dart';

class EndIncidentSheet extends StatefulWidget {
  const EndIncidentSheet({super.key});

  @override
  State<EndIncidentSheet> createState() => _EndIncidentSheetState();
}

class _EndIncidentSheetState extends State<EndIncidentSheet> {
  int _selected = 0;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final rows = [
      (MpIcons.flame, c.statusFireSoft, c.statusFire, 'Cháy thật, đã xử lý'),
      (
        MpIcons.shield,
        c.statusOkSoft,
        c.statusOk,
        'Đã kiểm tra, không có cháy',
      ),
      (MpIcons.flag, c.bgRaised, c.textSecondary, 'Báo nhầm'),
    ];
    return MpSheet(
      title: 'Kết quả thế nào?',
      subtitle: 'Giúp lịch sử chính xác và AI học tốt hơn.',
      spacing: 12,
      children: [
        for (final (i, (icon, well, glyph, label)) in rows.indexed)
          _OutcomeRow(
            icon: icon,
            well: well,
            glyph: glyph,
            label: label,
            hint: i == 2 ? 'Ví dụ: đèn xe, phản chiếu, hơi nước' : null,
            selected: i == _selected,
            onTap: () => setState(() => _selected = i),
          ),
        MpButton(
          label: 'Lưu vào lịch sử',
          onPressed: () => Navigator.of(context).pop(_selected),
        ),
      ],
    );
  }
}

class _OutcomeRow extends StatelessWidget {
  const _OutcomeRow({
    required this.icon,
    required this.well,
    required this.glyph,
    required this.label,
    required this.selected,
    required this.onTap,
    this.hint,
  });

  final String icon;
  final Color well;
  final Color glyph;
  final String label;
  final String? hint;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return Semantics(
      button: true,
      selected: selected,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: selected ? c.brandAccentSoft : c.bgCard,
            border: selected
                ? Border.all(color: c.brandAccent, width: 1.5)
                : null,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Row(
            spacing: 12,
            children: [
              Container(
                width: 40,
                height: 40,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: well,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: MpDuotoneIcon(
                  icon,
                  outline: glyph,
                  accent: glyph,
                  size: 22,
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  spacing: 2,
                  children: [
                    Text(
                      label,
                      style: t.body.copyWith(
                        fontWeight: FontWeight.w700,
                        color: c.textPrimary,
                      ),
                    ),
                    if (hint case final hint?)
                      Text(
                        hint,
                        style: t.caption.copyWith(
                          fontWeight: FontWeight.w500,
                          color: c.textSecondary,
                        ),
                      ),
                  ],
                ),
              ),
              if (hint != null) const MpChevron(),
            ],
          ),
        ),
      ),
    );
  }
}

class FalseAlarmReasonSheet extends StatefulWidget {
  const FalseAlarmReasonSheet({super.key});

  static const reasons = [
    'Đèn xe',
    'Phản chiếu',
    'Hơi nước',
    'Khói thuốc',
    'Lửa có kiểm soát',
    'Khác',
  ];

  @override
  State<FalseAlarmReasonSheet> createState() => _FalseAlarmReasonSheetState();
}

class _FalseAlarmReasonSheetState extends State<FalseAlarmReasonSheet> {
  int _selected = 0;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return MpSheet(
      spacing: 12,
      children: [
        Row(
          spacing: 12,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: SizedBox(
                width: 72,
                height: 46,
                child: OverflowBox(
                  maxHeight: double.infinity,
                  child: MpIllustration(
                    MpIllustrations.learn,
                    size: Size(72, 72 * 180 / 280),
                  ),
                ),
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                spacing: 2,
                children: [
                  Text(
                    'Vì sao là báo nhầm?',
                    style: t.headline.copyWith(
                      fontWeight: FontWeight.w700,
                      color: c.textPrimary,
                    ),
                  ),
                  Text(
                    'Giúp AI không lặp lại lỗi này.',
                    style: t.caption.copyWith(
                      fontWeight: FontWeight.w500,
                      color: c.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final (i, reason) in FalseAlarmReasonSheet.reasons.indexed)
              MpChip(
                label: reason,
                style: MpChipStyle.suggestion,
                selected: i == _selected,
                onTap: () => setState(() => _selected = i),
              ),
          ],
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 6,
          children: [
            Text(
              'Ghi chú (tuỳ chọn)',
              style: t.label.copyWith(color: c.textSecondary),
            ),
            Container(
              height: 52,
              padding: const EdgeInsets.symmetric(horizontal: 14),
              alignment: Alignment.centerLeft,
              decoration: BoxDecoration(
                color: c.bgCard,
                border: Border.all(color: c.lineSubtle),
                borderRadius: BorderRadius.circular(14),
              ),
              child: TextField(
                style: t.body.copyWith(
                  fontWeight: FontWeight.w500,
                  color: c.textPrimary,
                ),
                decoration: InputDecoration.collapsed(
                  hintText: 'VD: xe vừa bật đèn khi vào hầm',
                  hintStyle: t.body.copyWith(
                    fontWeight: FontWeight.w500,
                    color: c.textMuted,
                  ),
                ),
              ),
            ),
          ],
        ),
        MpButton(
          label: 'Gửi báo nhầm',
          onPressed: () => Navigator.of(
            context,
          ).pop(FalseAlarmReasonSheet.reasons[_selected]),
        ),
      ],
    );
  }
}
