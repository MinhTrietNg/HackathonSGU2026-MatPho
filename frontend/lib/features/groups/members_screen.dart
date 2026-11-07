library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_page.dart';
import '../../data/models/group.dart';
import '../../data/providers.dart';
import 'group_dialogs.dart';
import 'group_routes.dart';
import 'group_state.dart';
import 'group_widgets.dart';
import 'nickname_sheet.dart';

class MembersScreen extends ConsumerWidget {
  const MembersScreen({super.key});

  void _back(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(GroupRoutes.groups);
    }
  }

  Future<void> _editOwnNickname(
    BuildContext context,
    WidgetRef ref,
    Group group,
    Member me,
  ) async {
    final choice = await showNicknameSheet(
      context,
      title: 'Tên của bạn',
      subtitle: 'Cả nhóm sẽ thấy tên này.',
      initialNickname: me.nickname ?? '',
      realName: me.realName ?? me.displayName,
    );
    if (choice == null || !context.mounted) return;
    await runGroupAction(
      context,
      () => ref
          .read(groupActionsProvider)
          .setNickname(
            groupId: group.id,
            memberId: me.id,
            nickname: choice.nickname,
          ),
    );
  }

  Future<void> _dissolve(
    BuildContext context,
    WidgetRef ref,
    Group group,
  ) async {
    if (!await confirmDissolveGroup(context) ||
        !context.mounted ||
        !isSelectedGroup(ref, group.id)) {
      return;
    }
    final done = await runGroupAction(
      context,
      () => ref.read(groupActionsProvider).dissolveGroup(group.id),
    );
    if (done && context.mounted) context.go(GroupRoutes.groups);
  }

  Future<void> _leave(BuildContext context, WidgetRef ref, Group group) async {
    if (!await confirmLeaveGroup(context, groupDisplayName(group)) ||
        !context.mounted ||
        !isSelectedGroup(ref, group.id)) {
      return;
    }
    final done = await runGroupAction(
      context,
      () => ref.read(groupActionsProvider).leaveGroup(group.id),
    );
    if (done && context.mounted) context.go(GroupRoutes.groups);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.mpColors;
    final t = context.mpText;
    final view = ref.watch(selectedGroupViewProvider);
    final group = view?.group;
    final header = MpHeader.back(
      title: group == null ? 'Thành viên' : groupDisplayName(group),
      onBack: () => _back(context),
    );
    if (view == null || group == null) {
      return MpPage(
        header: header,
        headerBottom: 10,
        gap: 10,
        children: const [],
      );
    }
    final (selectedId: _, group: _, :members, :cameras, :areas) = view;
    final now = ref.watch(clockProvider)();
    final canManage = group.myRole.canManage;
    final isOwner = group.myRole == GroupRole.owner;

    bool opensAccess(Member m) =>
        canManage && !m.isYou && !m.pending && m.role != GroupRole.owner;

    VoidCallback? tapFor(Member m) {
      if (m.isYou) return () => _editOwnNickname(context, ref, group, m);
      if (opensAccess(m)) {
        return () => context.push(GroupRoutes.member(m.id));
      }
      return null;
    }

    return MpPage(
      header: header,
      headerBottom: 10,
      gap: 10,
      children: [
        for (final m in members)
          GroupMemberCard(
            member: m,
            subtitle: memberSubtitle(
              m,
              cameras: cameras,
              areas: areas,
              now: now,
            ),
            onTap: tapFor(m),
            chevron: opensAccess(m),
          ),
        const Spacer(),
        if (!canManage)
          Text(
            groupPermissionNote,
            textAlign: TextAlign.center,
            style: t.caption.copyWith(
              fontWeight: FontWeight.w500,
              height: 1.3,
              color: c.textMuted,
            ),
          ),
        if (canManage)
          MpButton(
            label: 'Mời thành viên',
            icon: MpIcons.plus,
            onPressed: () => context.push(GroupRoutes.invite),
          ),
        if (isOwner)
          MpButton(
            label: 'Giải tán nhóm',
            icon: MpIcons.trash,
            kind: MpButtonKind.quiet,
            size: MpButtonSize.m,
            onPressed: () => _dissolve(context, ref, group),
          )
        else
          MpButton(
            label: 'Rời nhóm',
            icon: MpIcons.logout,
            kind: MpButtonKind.secondary,
            onPressed: () => _leave(context, ref, group),
          ),
      ],
    );
  }
}
