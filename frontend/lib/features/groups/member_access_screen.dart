library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_ceil_width.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_section_label.dart';
import '../../core/widgets/mp_toggle.dart';
import '../../data/models/models.dart';
import 'group_dialogs.dart';
import 'group_state.dart';
import 'group_widgets.dart';
import 'nickname_sheet.dart';

class MemberAccessScreen extends ConsumerWidget {
  const MemberAccessScreen({super.key, required this.memberId});

  final String memberId;

  Future<void> _editNickname(
    BuildContext context,
    WidgetRef ref,
    Group group,
    Member m,
  ) async {
    final real = m.realName;
    final choice = await showNicknameSheet(
      context,
      title: 'Tên của ${m.displayName}',
      subtitle: real == null ? '' : 'Tên thật: $real.',
      initialNickname: m.nickname ?? '',
      realName: real ?? m.displayName,
      suggestions: nicknameSuggestions(m),
    );
    if (choice == null || !context.mounted) return;
    await runGroupAction(
      context,
      () => ref
          .read(groupActionsProvider)
          .setNickname(
            groupId: group.id,
            memberId: m.id,
            nickname: choice.nickname,
          ),
    );
  }

  Future<void> _remove(
    BuildContext context,
    WidgetRef ref,
    Group group,
    Member m,
  ) async {
    if (!await confirmRemoveMember(context, m.displayName) ||
        !context.mounted ||
        !isSelectedGroup(ref, group.id)) {
      return;
    }
    final done = await runGroupAction(
      context,
      () => ref
          .read(groupActionsProvider)
          .removeMember(groupId: group.id, memberId: m.id),
    );
    if (done && context.mounted) context.pop();
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = context.mpColors;
    final t = context.mpText;
    final view = ref.watch(selectedGroupViewProvider);
    final m = view?.members.where((m) => m.id == memberId).firstOrNull;
    if (view == null || m == null) {
      return MpPage(
        header: MpHeader.back(title: '', onBack: () => context.pop()),
        headerBottom: 10,
        gap: 10,
        children: const [],
      );
    }
    final (selectedId: _, :group, members: _, :cameras, :areas) = view;
    final actions = ref.read(groupActionsProvider);
    final real = m.realName;
    final ids = m.cameraIds;
    final perCamera =
        m.role == GroupRole.member || m.role == GroupRole.alertsOnly;

    return MpPage(
      header: MpHeader.back(title: m.displayName, onBack: () => context.pop()),
      headerBottom: 10,
      gap: 10,
      children: [
        Row(
          spacing: 12,
          children: [
            Container(
              width: 48,
              height: 48,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: c.bgRaised,
                shape: BoxShape.circle,
              ),
              child: ExcludeSemantics(
                child: Text(
                  memberInitial(m),
                  style: t.headline.copyWith(
                    fontWeight: FontWeight.w700,
                    color: c.textPrimary,
                  ),
                ),
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                spacing: 2,
                children: [
                  Text(
                    [?real, maskPhone(m.phone)].join(' · '),
                    style: t.body.copyWith(
                      fontWeight: FontWeight.w500,
                      color: c.textSecondary,
                    ),
                  ),
                  GroupRoleTag(m.role),
                ],
              ),
            ),
          ],
        ),
        if (group.myRole == GroupRole.owner) ...[
          const MpSectionLabel('TÊN TRONG NHÓM'),
          GroupListRow(
            icon: MpIcons.edit,
            iconColor: c.brandAccent,
            title: m.displayName,
            subtitle: real == null ? null : 'Tên thật: $real',
            trailing: MpCeilWidth(
              child: Text(
                'Sửa',
                style: t.label.copyWith(color: c.brandAccentFg),
              ),
            ),
            onTap: () => _editNickname(context, ref, group, m),
          ),
        ],
        const MpSectionLabel('VAI TRÒ'),
        _RoleSegments(
          selected: m.role,
          onChanged: (role) => runGroupAction(
            context,
            () =>
                actions.setRole(groupId: group.id, memberId: m.id, role: role),
          ),
        ),
        if (perCamera && cameras.isNotEmpty) ...[
          const MpSectionLabel('CAMERA'),
          GroupRowStack(
            children: [
              for (final cam in cameras)
                GroupListRow(
                  icon: MpIcons.camera,
                  iconColor: c.textSecondary,
                  title: cameraLabel(cam, areas),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 8,
                  ),
                  radius: 0,
                  trailing: MpToggle(
                    value: ids == null || ids.contains(cam.id),
                    semanticLabel: cameraLabel(cam, areas),
                    onChanged: (on) => runGroupAction(
                      context,
                      () => actions.setCameraAccess(
                        groupId: group.id,
                        memberId: m.id,
                        cameraId: cam.id,
                        enabled: on,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ],
        const Spacer(),
        MpButton(
          label: 'Xoá khỏi nhóm',
          icon: MpIcons.trash,
          kind: MpButtonKind.secondary,
          onPressed: () => _remove(context, ref, group, m),
        ),
      ],
    );
  }
}

class _RoleSegments extends StatelessWidget {
  const _RoleSegments({required this.selected, required this.onChanged});

  final GroupRole selected;
  final ValueChanged<GroupRole> onChanged;

  static const _roles = [
    GroupRole.manager,
    GroupRole.member,
    GroupRole.alertsOnly,
  ];

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        spacing: 4,
        children: [
          for (final role in _roles)
            Expanded(
              child: Semantics(
                button: true,
                selected: role == selected,
                label: roleLabel(role),
                excludeSemantics: true,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: role == selected ? null : () => onChanged(role),
                  child: Container(
                    height: 36,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: role == selected ? c.brandAccent : null,
                      borderRadius: BorderRadius.circular(9),
                    ),
                    child: Text(
                      roleLabel(role),
                      maxLines: 1,
                      style: context.mpText.label.copyWith(
                        color: role == selected
                            ? c.brandOnAccent
                            : c.textSecondary,
                      ),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
