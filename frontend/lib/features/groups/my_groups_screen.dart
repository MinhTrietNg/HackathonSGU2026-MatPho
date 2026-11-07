library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_badge.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_section_label.dart';
import '../../core/widgets/mp_toast.dart';
import '../../data/models/group.dart';
import 'current_group.dart';
import 'group_dialogs.dart';
import 'group_routes.dart';
import 'group_state.dart';
import 'group_widgets.dart';
import 'pending_declines.dart';

const _toastBottom = 28.0;

void showJoinedGroupToast(
  BuildContext context,
  String groupName, {
  Duration? duration = MpToast.undoDuration,
}) {
  final c = context.mpColors;
  showMpToast(
    context,
    MpToast(
      icon: MpDuotoneIcon(
        MpIcons.check,
        outline: c.textPrimary,
        accent: c.textPrimary,
        size: 18,
      ),
      title: 'Đã vào nhóm $groupName',
    ),
    duration: duration,
    bottom: _toastBottom,
  );
}

void showDeclinedInvitationToast(
  BuildContext context,
  String groupName, {
  required VoidCallback onUndo,
  Duration? duration = MpToast.undoDuration,
}) {
  final c = context.mpColors;
  showMpToast(
    context,
    MpToast(
      icon: MpDuotoneIcon(
        MpIcons.close,
        outline: c.textPrimary,
        accent: c.textPrimary,
        size: 18,
      ),
      title: 'Đã từ chối lời mời · ${shortGroupName(groupName)}',
      actionLabel: 'Hoàn tác',
      onAction: onUndo,
    ),
    duration: duration,
    bottom: _toastBottom,
  );
}

class MyGroupsScreen extends ConsumerStatefulWidget {
  const MyGroupsScreen({super.key});

  @override
  ConsumerState<MyGroupsScreen> createState() => _MyGroupsScreenState();
}

class _MyGroupsScreenState extends ConsumerState<MyGroupsScreen> {
  late final AppLifecycleListener _lifecycle;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_reload());
    });
    _lifecycle = AppLifecycleListener(onResume: () => unawaited(_reload()));
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    super.dispose();
  }

  Future<void> _reload() => ref.read(groupActionsProvider).reload();

  final _answering = <String>{};

  Future<void> _accept(Invitation invitation) async {
    setState(() => _answering.add(invitation.id));
    final done = await runGroupAction(
      context,
      () => ref
          .read(groupActionsProvider)
          .acceptInvitation(invitation.id, makeCurrent: false),
    );
    if (!mounted) return;
    setState(() => _answering.remove(invitation.id));
    if (!done) {
      unawaited(_reload());
      return;
    }
    showJoinedGroupToast(context, invitation.groupName);
  }

  Future<void> _decline(Invitation invitation) async {
    final confirmed = await confirmDeclineInvitation(
      context,
      invitation.inviterName,
    );
    if (!confirmed || !mounted) return;
    final pending = ref.read(pendingDeclinesProvider.notifier)
      ..schedule(invitation.id);
    showDeclinedInvitationToast(
      context,
      invitation.groupName,
      onUndo: () => pending.cancel(invitation.id),
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final groups = [
      for (final g in ref.watch(groupsProvider).value ?? const <Group>[])
        if (!g.isPersonal) g,
    ];
    final declining = ref.watch(pendingDeclinesProvider);
    final invitations = [
      for (final i
          in ref.watch(myInvitationsProvider).value ?? const <Invitation>[])
        if (!declining.contains(i.id)) i,
    ];
    final current = ref.watch(currentGroupProvider).value;
    final account = ref.watch(groupAccountProvider);

    return MpPage(
      header: MpHeader.back(
        title: 'Nhóm & thành viên',
        onBack: () =>
            context.canPop() ? context.pop() : context.go(AppRoutes.settings),
      ),
      headerBottom: 14,
      gap: 14,
      onRefresh: _reload,
      children: [
        Text(
          'Mỗi nhóm có camera và người riêng.',
          style: t.caption.copyWith(
            fontWeight: FontWeight.w500,
            color: c.textSecondary,
          ),
        ),
        _ActionCard(
          icon: MpIcons.plus,
          title: 'Tạo nhóm',
          subtitle: 'Nhà, toà nhà, cửa hàng',
          onTap: () => context.push(GroupRoutes.createGroup),
        ),
        if (invitations.isNotEmpty) ...[
          MpSectionLabel('LỜI MỜI · ${invitations.length}'),
          for (final invitation in invitations)
            _InvitationCard(
              invitation: invitation,
              busy: _answering.contains(invitation.id),
              onOpen: () => context.push(GroupRoutes.invitation(invitation.id)),
              onDecline: () => _decline(invitation),
              onAccept: () => _accept(invitation),
            ),
        ],
        MpSectionLabel('NHÓM CỦA BẠN · ${groups.length}'),
        for (final g in groups)
          GroupListRow(
            icon: g.id == current?.id ? MpIcons.shield : MpIcons.user,
            iconColor: c.brandAccent,
            title: groupDisplayName(g),
            subtitle: groupRowSubtitle(g, accountName: account?.fullName ?? ''),
            badge: MpBadge(
              label: roleLabel(g.myRole),
              tone: g.myRole.canManage
                  ? MpBadgeTone.accent
                  : MpBadgeTone.neutral,
            ),
            trailing: const MpChevron(),
            onTap: () {
              ref.read(currentGroupIdProvider.notifier).select(g.id);
              context.push(GroupRoutes.members);
            },
          ),
        const Spacer(),
      ],
    );
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final String icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final glyph = c.brandOnAccent;
    return MergeSemantics(
      child: Semantics(
        button: true,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: c.bgCard,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: c.brandAccent),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              spacing: 10,
              children: [
                Container(
                  width: 40,
                  height: 40,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: c.brandAccent,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: MpDuotoneIcon(
                    icon,
                    outline: glyph,
                    accent: glyph,
                    size: 20,
                  ),
                ),
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
        ),
      ),
    );
  }
}

class _InvitationCard extends StatelessWidget {
  const _InvitationCard({
    required this.invitation,
    required this.busy,
    required this.onOpen,
    required this.onDecline,
    required this.onAccept,
  });

  final Invitation invitation;
  final bool busy;
  final VoidCallback onOpen;
  final VoidCallback onDecline;
  final VoidCallback onAccept;

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 12,
        children: [
          GroupListRow(
            icon: MpIcons.user,
            iconColor: c.brandAccent,
            title: invitation.groupName,
            subtitle: invitationRowSubtitle(invitation),
            badge: MpBadge(
              label: roleLabel(invitation.role),
              tone: MpBadgeTone.neutral,
            ),
            trailing: const MpChevron(),
            padding: EdgeInsets.zero,
            radius: 0,
            onTap: onOpen,
          ),
          Row(
            spacing: 10,
            children: [
              Expanded(
                child: MpButton(
                  label: 'Từ chối',
                  kind: MpButtonKind.secondary,
                  size: MpButtonSize.m,
                  onPressed: busy ? null : onDecline,
                ),
              ),
              Expanded(
                child: MpButton(
                  label: 'Chấp nhận',
                  size: MpButtonSize.m,
                  onPressed: busy ? null : onAccept,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
