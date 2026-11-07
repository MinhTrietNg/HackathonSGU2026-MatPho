import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../data/models/models.dart';
import 'ai_mode_state.dart';

class AiCountCard extends StatelessWidget {
  const AiCountCard({super.key, required this.count, required this.subtitle});

  final int count;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return MergeSemantics(
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: c.bgCard,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          spacing: 14,
          children: [
            Text(
              '$count',
              style: t.display.copyWith(
                fontWeight: FontWeight.w800,
                color: c.textPrimary,
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                spacing: 2,
                children: [
                  Text(
                    'camera đã kết nối',
                    style: t.body.copyWith(
                      fontWeight: FontWeight.w700,
                      color: c.textPrimary,
                    ),
                  ),
                  Text(
                    subtitle,
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
      ),
    );
  }
}

class AiLockedNote extends StatelessWidget {
  const AiLockedNote({super.key, this.ownerName});

  final String? ownerName;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final owner = ownerName;
    return MergeSemantics(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: c.bgCard,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: c.lineSubtle),
        ),
        child: Row(
          spacing: 10,
          children: [
            MpDuotoneIcon(
              MpIcons.lock,
              outline: c.textPrimary,
              accent: c.textPrimary,
              size: 18,
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                spacing: 2,
                children: [
                  Text(
                    'Chỉ chủ nhóm được đổi cài đặt AI',
                    style: t.caption.copyWith(
                      fontWeight: FontWeight.w700,
                      color: c.textPrimary,
                    ),
                  ),
                  Text(
                    owner == null
                        ? 'Muốn đổi, nhắn chủ nhóm.'
                        : 'Muốn đổi, nhắn $owner (chủ nhóm).',
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
      ),
    );
  }
}

const aiOffWarning =
    'Có cháy ở đây sẽ không ai được báo. '
    'Chỉ nên tắt khi camera bị che hoặc đang sửa.';

class AiModePicker extends StatelessWidget {
  const AiModePicker({super.key, required this.value, required this.onChanged});

  final CameraAi value;
  final ValueChanged<CameraAi> onChanged;

  void _select(AiMode mode) {
    final pauses = mode == AiMode.scheduled && value.pauses.isEmpty
        ? const [defaultAiPause]
        : value.pauses;
    onChanged(CameraAi(mode: mode, pauses: pauses));
  }

  void _setPause(int index, AiPause pause) => onChanged(
    CameraAi(
      mode: value.mode,
      pauses: [
        for (final (i, p) in value.pauses.indexed) i == index ? pause : p,
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final mode = value.mode;
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 2,
        children: [
          _Option(
            title: 'Luôn bật AI',
            subtitle: 'Báo cháy 24/7',
            selected: mode == AiMode.alwaysOn,
            onTap: () => _select(AiMode.alwaysOn),
          ),
          _Option(
            title: 'Nghỉ AI theo giờ',
            subtitle: 'Ngoài khung giờ vẫn báo cháy bình thường',
            selected: mode == AiMode.scheduled,
            onTap: () => _select(AiMode.scheduled),
            child: mode != AiMode.scheduled
                ? null
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    spacing: 12,
                    children: [
                      for (final (i, pause) in value.pauses.indexed)
                        _PauseEditor(
                          label: value.pauses.length > 1
                              ? 'KHUNG GIỜ ${i + 1}'
                              : null,
                          pause: pause,
                          onFrom: (m) => _setPause(i, pause.copyWith(from: m)),
                          onTo: (m) => _setPause(i, pause.copyWith(to: m)),
                          onDays: (days) =>
                              _setPause(i, pause.copyWith(days: days)),
                          onRemove: i == 0
                              ? null
                              : () => onChanged(
                                  CameraAi(
                                    mode: mode,
                                    pauses: [...value.pauses]..removeAt(i),
                                  ),
                                ),
                        ),
                      if (value.pauses.length < maxAiPauses)
                        _TextAction(
                          label: '+ Thêm khung giờ',
                          color: c.brandAccentFg,
                          onTap: () => onChanged(
                            CameraAi(
                              mode: mode,
                              pauses: [...value.pauses, extraAiPause],
                            ),
                          ),
                        ),
                    ],
                  ),
          ),
          _Option(
            title: 'Tắt hẳn AI',
            subtitle: 'Camera này không báo cháy nữa',
            selected: mode == AiMode.off,
            onTap: () => _select(AiMode.off),
            child: mode != AiMode.off
                ? null
                : Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 8,
                    ),
                    decoration: BoxDecoration(
                      color: c.statusWarnSoft,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      aiOffWarning,
                      style: t.caption.copyWith(
                        fontWeight: FontWeight.w500,
                        color: c.statusWarn,
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _Option extends StatelessWidget {
  const _Option({
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
    this.child,
  });

  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;
  final Widget? child;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final header = Semantics(
      button: true,
      selected: selected,
      child: MergeSemantics(
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: Row(
            spacing: 12,
            children: [
              _Radio(selected: selected),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  spacing: 2,
                  children: [
                    Text(
                      title,
                      style: t.body.copyWith(
                        fontWeight: FontWeight.w700,
                        color: c.textPrimary,
                      ),
                    ),
                    Text(
                      subtitle,
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
        ),
      ),
    );
    final child = this.child;
    return Container(
      color: c.bgCard,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: child == null
          ? header
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              spacing: 12,
              children: [
                header,
                Padding(padding: const EdgeInsets.only(left: 32), child: child),
              ],
            ),
    );
  }
}

class _Radio extends StatelessWidget {
  const _Radio({required this.selected});

  final bool selected;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Container(
      width: 20,
      height: 20,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: selected ? c.brandAccent : c.textMuted,
          width: 2,
        ),
      ),
      child: selected
          ? Container(
              width: 10,
              height: 10,
              decoration: BoxDecoration(
                color: c.brandAccent,
                shape: BoxShape.circle,
              ),
            )
          : null,
    );
  }
}

class _PauseEditor extends StatelessWidget {
  const _PauseEditor({
    required this.label,
    required this.pause,
    required this.onFrom,
    required this.onTo,
    required this.onDays,
    required this.onRemove,
  });

  final String? label;
  final AiPause pause;
  final ValueChanged<int> onFrom;
  final ValueChanged<int> onTo;
  final ValueChanged<Set<int>> onDays;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final label = this.label;
    final onRemove = this.onRemove;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      spacing: 8,
      children: [
        if (label != null)
          Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: t.caption.copyWith(
                    fontWeight: FontWeight.w700,
                    color: c.textMuted,
                  ),
                ),
              ),
              if (onRemove != null)
                _TextAction(
                  label: 'Xoá',
                  color: c.statusWarn,
                  semanticLabel: 'Xoá ${label.toLowerCase()}',
                  onTap: onRemove,
                ),
            ],
          ),
        Row(
          spacing: 8,
          children: [
            Expanded(
              child: AiTimeBox(
                label: 'Từ',
                minute: pause.from,
                onChanged: onFrom,
              ),
            ),
            Expanded(
              child: AiTimeBox(label: 'Đến', minute: pause.to, onChanged: onTo),
            ),
          ],
        ),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final MapEntry(key: day, value: name) in weekdayLabels.entries)
              AiDayChip(
                label: name,
                on: pause.days.contains(day),
                onTap: () => onDays(
                  pause.days.contains(day)
                      ? ({...pause.days}..remove(day))
                      : {...pause.days, day},
                ),
              ),
          ],
        ),
      ],
    );
  }
}

// Typed in place, like the alarm editors of the big clock apps: tap the hour,
// type two digits, the cursor jumps to the minutes. Each valid number is taken
// as it is typed; an invalid one goes back to the last value on leaving.
class AiTimeBox extends StatefulWidget {
  const AiTimeBox({
    super.key,
    required this.label,
    required this.minute,
    required this.onChanged,
  });

  final String label;
  final int minute;
  final ValueChanged<int> onChanged;

  @override
  State<AiTimeBox> createState() => _AiTimeBoxState();
}

class _AiTimeBoxState extends State<AiTimeBox> {
  late final _hour = TextEditingController(text: _two(widget.minute ~/ 60));
  late final _min = TextEditingController(text: _two(widget.minute % 60));
  final _hourFocus = FocusNode();
  final _minFocus = FocusNode();

  static String _two(int n) => n.toString().padLeft(2, '0');

  @override
  void initState() {
    super.initState();
    _hourFocus.addListener(() => _focusChanged(_hourFocus, _hour));
    _minFocus.addListener(() => _focusChanged(_minFocus, _min));
  }

  @override
  void didUpdateWidget(AiTimeBox old) {
    super.didUpdateWidget(old);
    if (old.minute != widget.minute && !_editing) _reset();
  }

  @override
  void dispose() {
    _hour.dispose();
    _min.dispose();
    _hourFocus.dispose();
    _minFocus.dispose();
    super.dispose();
  }

  bool get _editing => _hourFocus.hasFocus || _minFocus.hasFocus;

  void _reset() {
    _hour.text = _two(widget.minute ~/ 60);
    _min.text = _two(widget.minute % 60);
  }

  void _focusChanged(FocusNode node, TextEditingController field) {
    setState(() {});
    if (node.hasFocus) {
      field.selection = TextSelection(
        baseOffset: 0,
        extentOffset: field.text.length,
      );
    } else if (!_editing) {
      _reset();
    }
  }

  void _hourTyped(String text) {
    final hour = int.tryParse(text);
    if (hour == null || hour > 23) return;
    widget.onChanged(hour * 60 + widget.minute % 60);
    if (text.length == 2) _minFocus.requestFocus();
  }

  void _minuteTyped(String text) {
    final minute = int.tryParse(text);
    if (minute == null || minute > 59) return;
    widget.onChanged(widget.minute ~/ 60 * 60 + minute);
    if (text.length == 2) _minFocus.unfocus();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final digits = t.title.copyWith(
      fontWeight: FontWeight.w800,
      color: c.textPrimary,
    );
    Widget field(
      String part,
      TextEditingController controller,
      FocusNode focus,
      ValueChanged<String> onChanged, {
      TextAlign align = TextAlign.start,
    }) => Semantics(
      label: '${widget.label}, $part',
      child: SizedBox(
        width: 36,
        child: TextField(
          controller: controller,
          focusNode: focus,
          onChanged: onChanged,
          style: digits,
          textAlign: align,
          cursorColor: c.brandAccent,
          keyboardType: TextInputType.number,
          inputFormatters: [
            FilteringTextInputFormatter.digitsOnly,
            LengthLimitingTextInputFormatter(2),
          ],
          enableInteractiveSelection: false,
          decoration: InputDecoration.collapsed(
            hintText: '00',
            hintStyle: digits.copyWith(color: c.textMuted),
          ),
          onTapOutside: (_) => focus.unfocus(),
        ),
      ),
    );
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => _hourFocus.requestFocus(),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: c.bgRaised,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: _editing ? c.brandAccent : c.bgRaised,
            width: 1.5,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.label,
              style: t.caption.copyWith(
                fontWeight: FontWeight.w500,
                color: c.textSecondary,
              ),
            ),
            Row(
              children: [
                field(
                  'giờ',
                  _hour,
                  _hourFocus,
                  _hourTyped,
                  align: TextAlign.end,
                ),
                Text(':', style: digits),
                field('phút', _min, _minFocus, _minuteTyped),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class AiDayChip extends StatelessWidget {
  const AiDayChip({
    super.key,
    required this.label,
    required this.on,
    required this.onTap,
  });

  final String label;
  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Semantics(
      button: true,
      selected: on,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          width: 29,
          height: 29,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: on ? c.brandAccent : c.bgRaised,
            shape: BoxShape.circle,
          ),
          child: Text(
            label,
            style: context.mpText.caption.copyWith(
              fontWeight: FontWeight.w700,
              color: on ? c.brandOnAccent : c.textMuted,
            ),
          ),
        ),
      ),
    );
  }
}

class _TextAction extends StatelessWidget {
  const _TextAction({
    required this.label,
    required this.color,
    required this.onTap,
    this.semanticLabel,
  });

  final String label;
  final Color color;
  final VoidCallback onTap;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semanticLabel ?? label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Text(label, style: context.mpText.label.copyWith(color: color)),
      ),
    );
  }
}
