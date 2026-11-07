library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_ceil_width.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_text_field.dart';
import '../../data/errors.dart';
import '../../data/models/models.dart';
import 'group_state.dart';
import 'group_widgets.dart';

const notRegisteredHint = 'Số này chưa có tài khoản Mắt Phố';

const alreadyInGroupHint = 'Số này đã ở trong nhóm';

class InviteMemberScreen extends ConsumerStatefulWidget {
  const InviteMemberScreen({
    super.key,
    this.initialPhone,
    this.initialNickname,
    this.initialRole = GroupRole.member,
    this.initialAreaIds,
    this.previewFocused = false,
  });

  final String? initialPhone;
  final String? initialNickname;
  final GroupRole initialRole;

  final Set<String>? initialAreaIds;

  final bool previewFocused;

  @override
  ConsumerState<InviteMemberScreen> createState() => _InviteMemberScreenState();
}

class _InviteMemberScreenState extends ConsumerState<InviteMemberScreen> {
  late final _phone = TextEditingController(
    text: widget.initialPhone == null
        ? null
        : formatPhone(widget.initialPhone!),
  );
  late final _nickname = TextEditingController(text: widget.initialNickname);
  late GroupRole _role = widget.initialRole;

  late Set<String>? _areaIds = widget.initialAreaIds == null
      ? null
      : {...widget.initialAreaIds!};

  Set<String> _chosen(List<Area> areas) =>
      _areaIds ?? {for (final a in areas) a.id};
  String? _phoneError;
  bool _sending = false;

  @override
  void dispose() {
    _phone.dispose();
    _nickname.dispose();
    super.dispose();
  }

  Future<void> _send(CurrentGroupView view) async {
    final (:group, members: _, :cameras, :areas) = view;
    final chosen = _chosen(areas);
    final phone = _phone.text.replaceAll(' ', '');
    if (!isValidVnPhone(phone)) {
      setState(() => _phoneError = 'Số điện thoại cần đủ 10 số');
      return;
    }
    final cameraIds = _role.canManage
        ? const <String>[]
        : [
            for (final c in cameras)
              if (chosen.contains(c.areaId)) c.id,
          ];
    final nickname = _nickname.text.trim();
    setState(() => _sending = true);
    String? inlineError;
    final done = await runGroupAction(context, () async {
      try {
        await ref
            .read(groupActionsProvider)
            .inviteMember(
              groupId: group.id,
              phone: phone,
              role: _role,
              cameraIds: cameraIds,
              nickname: nickname.isEmpty ? null : nickname,
            );
      } on PhoneNotRegisteredException {
        inlineError = notRegisteredHint;
      } on AlreadyInGroupException {
        inlineError = alreadyInGroupHint;
      }
    });
    if (!mounted) return;
    setState(() {
      _sending = false;
      if (inlineError != null) _phoneError = inlineError;
    });
    if (done && inlineError == null) context.pop();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final view = ref.watch(currentGroupViewProvider).value;
    final group = view?.group;
    final areas = view?.areas ?? const <Area>[];
    final label = t.label.copyWith(color: c.textSecondary);

    return MpPage(
      header: MpHeader.back(
        title: group == null
            ? ''
            : 'Mời vào ${shortGroupName(groupDisplayName(group))}',
        onBack: () => context.pop(),
      ),
      headerBottom: 12,
      gap: 12,
      children: [
        MpTextField(
          label: 'Số điện thoại',
          icon: MpIcons.phone,
          controller: _phone,
          keyboardType: TextInputType.phone,
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp(r'[0-9 ]')),
          ],
          autofillHints: const [AutofillHints.telephoneNumber],
          errorText: _phoneError,
          onChanged: (_) {
            if (_phoneError != null) setState(() => _phoneError = null);
          },
          state: widget.previewFocused ? MpFieldState.focused : null,
        ),
        MpTextField(
          label: 'Tên trong nhóm · không bắt buộc',
          icon: MpIcons.edit,
          controller: _nickname,
          textInputAction: TextInputAction.done,
        ),
        Text('Vai trò', style: label),
        for (final (role, subtitle) in const [
          (GroupRole.manager, 'Thêm camera, mời người'),
          (GroupRole.member, 'Xem camera, nhận báo cháy'),
          (GroupRole.alertsOnly, 'Không xem camera'),
        ])
          _RoleOption(
            title: roleLabel(role),
            subtitle: subtitle,
            selected: _role == role,
            onTap: () => setState(() => _role = role),
          ),
        if (_role != GroupRole.manager && areas.isNotEmpty) ...[
          Text('Camera', style: label),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final a in areas)
                _AreaChip(
                  label: a.name,
                  selected: _chosen(areas).contains(a.id),
                  onTap: () => setState(() {
                    final chosen = _chosen(areas);
                    if (!chosen.remove(a.id)) chosen.add(a.id);
                    _areaIds = chosen;
                  }),
                ),
            ],
          ),
        ],
        const Spacer(),
        MpButton(
          label: 'Mời qua app',
          icon: MpIcons.sms,
          onPressed:
              view == null ||
                  _sending ||
                  (!_role.canManage &&
                      areas.isNotEmpty &&
                      _chosen(areas).isEmpty)
              ? null
              : () => _send(view),
        ),
      ],
    );
  }
}

class _RoleOption extends StatelessWidget {
  const _RoleOption({
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return MergeSemantics(
      child: Semantics(
        button: true,
        selected: selected,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: selected ? c.brandAccentSoft : c.bgCard,
              borderRadius: BorderRadius.circular(14),
              border: selected
                  ? Border.all(color: c.brandAccent, width: 1.5)
                  : null,
            ),
            child: Row(
              spacing: 12,
              children: [
                GroupRadio(selected: selected),
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
      ),
    );
  }
}

class _AreaChip extends StatelessWidget {
  const _AreaChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            color: selected ? c.brandAccentSoft : c.bgCard,
            borderRadius: BorderRadius.circular(99),
            border: Border.all(color: selected ? c.brandAccent : c.lineSubtle),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            spacing: 6,
            children: [
              if (selected)
                MpDuotoneIcon(
                  MpIcons.check,
                  outline: c.brandAccent,
                  accent: c.brandAccent,
                  size: 14,
                ),
              MpCeilWidth(
                child: Text(
                  label,
                  style: context.mpText.label.copyWith(
                    color: selected ? c.brandAccentFg : c.textSecondary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
