library;

import 'package:flutter/material.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_ceil_width.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_sheet.dart';
import '../../core/widgets/mp_text_field.dart';
import 'group_widgets.dart';

typedef NicknameChoice = ({String? nickname});

Future<NicknameChoice?> showNicknameSheet(
  BuildContext context, {
  required String title,
  required String subtitle,
  required String initialNickname,
  required String realName,
  List<String> suggestions = const [],
  bool previewFocused = false,
}) => showMpSheet<NicknameChoice>(
  context,
  builder: (_) => NicknameSheet(
    title: title,
    subtitle: subtitle,
    initialNickname: initialNickname,
    realName: realName,
    suggestions: suggestions,
    previewFocused: previewFocused,
  ),
);

class NicknameSheet extends StatefulWidget {
  const NicknameSheet({
    super.key,
    required this.title,
    required this.subtitle,
    required this.initialNickname,
    required this.realName,
    this.suggestions = const [],
    this.previewFocused = false,
  });

  final String title;
  final String subtitle;
  final String initialNickname;
  final String realName;
  final List<String> suggestions;
  final bool previewFocused;

  @override
  State<NicknameSheet> createState() => _NicknameSheetState();
}

class _NicknameSheetState extends State<NicknameSheet> {
  late final _controller = TextEditingController(text: widget.initialNickname);
  var _useRealName = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _pick(String name) => setState(() {
    _controller.text = name;
    _useRealName = false;
  });

  void _save() {
    final text = _controller.text.trim();
    Navigator.of(context).pop<NicknameChoice>((
      nickname: _useRealName || text.isEmpty ? null : text,
    ));
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return MpSheet(
      children: [
        Semantics(
          header: true,
          child: Text(
            widget.title,
            style: t.headline.copyWith(
              fontWeight: FontWeight.w700,
              color: c.textPrimary,
            ),
          ),
        ),
        Text(
          widget.subtitle,
          style: t.caption.copyWith(
            fontWeight: FontWeight.w500,
            color: c.textSecondary,
          ),
        ),
        MpTextField(
          label: 'Tên trong nhóm',
          icon: MpIcons.edit,
          controller: _controller,
          textInputAction: TextInputAction.done,
          onChanged: (_) {
            if (_useRealName) setState(() => _useRealName = false);
          },
          onSubmitted: (_) => _save(),
          state: widget.previewFocused ? MpFieldState.focused : null,
        ),
        if (widget.suggestions.isNotEmpty)
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final s in widget.suggestions)
                _SuggestionChip(label: s, onTap: () => _pick(s)),
            ],
          ),
        GroupListRow(
          icon: MpIcons.user,
          iconColor: c.textPrimary,
          title: 'Dùng tên thật',
          subtitle: 'Hiện là "${widget.realName}"',
          trailing: GroupRadio(selected: _useRealName, size: 22),
          onTap: () => setState(() {
            _useRealName = true;
            _controller.clear();
          }),
        ),
        MpButton(label: 'Lưu', onPressed: _save),
      ],
    );
  }
}

class _SuggestionChip extends StatelessWidget {
  const _SuggestionChip({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
          decoration: BoxDecoration(
            color: c.bgCard,
            borderRadius: BorderRadius.circular(99),
            border: Border.all(color: c.lineSubtle),
          ),
          child: MpCeilWidth(
            child: Text(
              label,
              style: context.mpText.label.copyWith(color: c.textSecondary),
            ),
          ),
        ),
      ),
    );
  }
}
