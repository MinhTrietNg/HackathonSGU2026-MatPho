import 'package:flutter/material.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_badge.dart';
import '../../core/widgets/mp_ceil_width.dart';
import '../../core/widgets/mp_dashed_border.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_toast.dart';
import '../../data/errors.dart';
import '../../data/models/group.dart';
import '../settings/settings_widgets.dart';
import 'group_state.dart';

class GroupMemberCard extends StatelessWidget {
  const GroupMemberCard({
    super.key,
    required this.member,
    required this.subtitle,
    this.onTap,
    this.chevron = false,
  });

  final Member member;
  final String subtitle;
  final VoidCallback? onTap;
  final bool chevron;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final pending = member.pending;
    Widget avatar = Container(
      width: 40,
      height: 40,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: c.bgRaised, shape: BoxShape.circle),
      child: ExcludeSemantics(
        child: Text(
          memberInitial(member),
          style: t.body.copyWith(
            fontWeight: FontWeight.w700,
            color: pending ? c.textMuted : c.textPrimary,
          ),
        ),
      ),
    );
    if (pending) {
      avatar = MpDashedBorder(color: c.lineStrong, radius: 20, child: avatar);
    }
    final card = Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        spacing: 12,
        children: [
          avatar,
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              spacing: 3,
              children: [
                Text(
                  memberTitle(member),
                  style: t.body.copyWith(
                    fontWeight: FontWeight.w700,
                    color: pending ? c.textSecondary : c.textPrimary,
                  ),
                ),
                if (subtitle.isNotEmpty)
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
          if (pending)
            const MpBadge(label: 'Chờ đồng ý', tone: MpBadgeTone.neutral)
          else
            GroupRoleTag(member.role),
          if (chevron) const MpChevron(),
        ],
      ),
    );
    return MergeSemantics(
      child: Semantics(
        button: onTap != null,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: card,
        ),
      ),
    );
  }
}

class GroupRoleTag extends StatelessWidget {
  const GroupRoleTag(this.role, {super.key});

  final GroupRole role;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final (bg, fg) = switch (role) {
      GroupRole.owner => (c.brandAccent, c.brandOnAccent),
      GroupRole.manager => (c.brandAccentSoft, c.brandAccentFg),
      GroupRole.member || GroupRole.alertsOnly => (c.bgRaised, c.textSecondary),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(99),
      ),
      child: MpCeilWidth(
        child: Text(
          roleLabel(role),
          style: context.mpText.label.copyWith(fontSize: 11, color: fg),
        ),
      ),
    );
  }
}

class GroupListRow extends StatelessWidget {
  const GroupListRow({
    super.key,
    required this.icon,
    required this.iconColor,
    required this.title,
    this.subtitle,
    this.badge,
    this.trailing,
    this.onTap,
    this.padding = const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
    this.radius = 14,
  });

  final String icon;
  final Color iconColor;
  final String title;
  final String? subtitle;
  final Widget? badge;
  final Widget? trailing;
  final VoidCallback? onTap;
  final EdgeInsets padding;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final row = Container(
      padding: padding,
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: radius == 0 ? null : BorderRadius.circular(radius),
      ),
      child: Row(
        spacing: 12,
        children: [
          Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: c.bgRaised,
              borderRadius: BorderRadius.circular(12),
            ),
            child: MpDuotoneIcon(
              icon,
              outline: iconColor,
              accent: iconColor,
              size: 22,
            ),
          ),
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
                if (subtitle case final subtitle?)
                  Text(
                    subtitle,
                    style: t.caption.copyWith(
                      fontWeight: FontWeight.w500,
                      color: c.textSecondary,
                    ),
                  ),
                ?badge,
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
    return MergeSemantics(
      child: Semantics(
        button: onTap != null,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: row,
        ),
      ),
    );
  }
}

class GroupRowStack extends StatelessWidget {
  const GroupRowStack({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 2,
        children: children,
      ),
    );
  }
}

class GroupRadio extends StatelessWidget {
  const GroupRadio({super.key, required this.selected, this.size = 20});

  final bool selected;
  final double size;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: selected ? c.brandAccent : c.lineStrong,
          width: 2,
        ),
      ),
      child: selected
          ? Container(
              width: size / 2,
              height: size / 2,
              decoration: BoxDecoration(
                color: c.brandAccent,
                shape: BoxShape.circle,
              ),
            )
          : null,
    );
  }
}

class GroupNicknameField extends StatefulWidget {
  const GroupNicknameField({
    super.key,
    required this.controller,
    required this.defaultName,
    this.defaultLabel = 'Mặc định',
    this.label = 'Tên của bạn trong nhóm',
  });

  final TextEditingController controller;

  final String defaultName;

  final String defaultLabel;
  final String label;

  @override
  State<GroupNicknameField> createState() => _GroupNicknameFieldState();
}

class _GroupNicknameFieldState extends State<GroupNicknameField> {
  final _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _focus.addListener(_changed);
    widget.controller.addListener(_changed);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_changed);
    _focus.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final value = t.body.copyWith(
      fontWeight: FontWeight.w500,
      color: c.textPrimary,
    );
    final focused = _focus.hasFocus;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 6,
      children: [
        Text(widget.label, style: t.label.copyWith(color: c.textSecondary)),
        Container(
          height: 52,
          padding: const EdgeInsets.symmetric(horizontal: 14),
          decoration: BoxDecoration(
            color: c.bgCard,
            borderRadius: BorderRadius.circular(14),
            border: focused
                ? Border.all(color: c.brandAccent, width: 1.5)
                : Border.all(color: c.lineSubtle),
          ),
          child: Row(
            spacing: 10,
            children: [
              MpDuotoneIcon(
                MpIcons.user,
                outline: c.textMuted,
                accent: c.textMuted,
                size: 20,
              ),
              Expanded(
                child: Semantics(
                  label: widget.label,
                  child: TextField(
                    controller: widget.controller,
                    focusNode: _focus,
                    textCapitalization: TextCapitalization.words,
                    style: value,
                    cursorColor: c.brandAccent,
                    decoration: InputDecoration.collapsed(
                      hintText: widget.defaultName,
                      hintStyle: value.copyWith(color: c.textMuted),
                    ),
                  ),
                ),
              ),
              if (widget.controller.text.isEmpty)
                MpCeilWidth(
                  child: Text(
                    widget.defaultLabel,
                    style: t.label.copyWith(color: c.brandAccentFg),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

void showGroupFailureToast(BuildContext context, Object error) {
  if (error is PermissionDeniedException) {
    final c = context.mpColors;
    showMpToast(
      context,
      MpToast(
        icon: MpDuotoneIcon(
          MpIcons.lock,
          outline: c.statusWarn,
          accent: c.statusWarn,
          size: 18,
        ),
        title: groupPermissionNote,
      ),
      duration: const Duration(seconds: 4),
    );
    return;
  }
  showSettingsFailureToast(context, error);
}

Future<bool> runGroupAction(
  BuildContext context,
  Future<void> Function() action,
) async {
  try {
    await action();
    return true;
  } on MpException catch (e) {
    if (context.mounted) showGroupFailureToast(context, e);
    return false;
  }
}

const groupPermissionNote =
    'Chỉ chủ nhóm và quản lý mới mời người hoặc thêm camera.';
