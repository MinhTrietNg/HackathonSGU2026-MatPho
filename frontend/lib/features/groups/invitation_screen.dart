library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_illustration.dart';
import '../../core/widgets/mp_page.dart';
import '../../data/models/models.dart';
import 'group_state.dart';
import 'group_widgets.dart';

class InvitationScreen extends ConsumerStatefulWidget {
  const InvitationScreen({super.key, required this.invitationId});

  final String invitationId;

  @override
  ConsumerState<InvitationScreen> createState() => _InvitationScreenState();
}

class _InvitationScreenState extends ConsumerState<InvitationScreen> {
  final _nickname = TextEditingController();
  bool _busy = false;

  static const _artSize = Size(260, 260 * 180 / 280);

  @override
  void dispose() {
    _nickname.dispose();
    super.dispose();
  }

  Future<void> _answer({required bool accept}) async {
    setState(() => _busy = true);
    final actions = ref.read(groupActionsProvider);
    final nickname = _nickname.text.trim();
    final done = await runGroupAction(
      context,
      () => accept
          ? actions.acceptInvitation(
              widget.invitationId,
              nickname: nickname.isEmpty ? null : nickname,
            )
          : actions.declineInvitation(widget.invitationId),
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (done) context.go(AppRoutes.monitor);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final invitation = ref.watch(invitationProvider(widget.invitationId));
    final account = ref.watch(groupAccountProvider);
    final value = invitation.value;
    if (value == null) {
      return MpPage(
        gap: 12,
        children: [
          if (invitation.hasError)
            Expanded(
              child: Center(
                child: Text(
                  'Lời mời không còn hiệu lực.',
                  textAlign: TextAlign.center,
                  style: t.body.copyWith(
                    fontWeight: FontWeight.w500,
                    color: c.textSecondary,
                  ),
                ),
              ),
            ),
        ],
      );
    }
    final suggested = value.nickname;
    return MpPage(
      gap: 12,
      children: [
        const Spacer(),
        const Center(
          child: MpIllustration(MpIllustrations.share, size: _artSize),
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 6,
          children: [
            Semantics(
              header: true,
              child: Text(
                '${value.inviterName} mời bạn vào "${value.groupName}"',
                textAlign: TextAlign.center,
                style: t.title.copyWith(
                  fontWeight: FontWeight.w800,
                  color: c.textPrimary,
                ),
              ),
            ),
            Text(
              'Vai trò: ${roleLabel(value.role)}',
              textAlign: TextAlign.center,
              style: t.body.copyWith(
                fontWeight: FontWeight.w500,
                color: c.textSecondary,
              ),
            ),
          ],
        ),
        _AccessCard(invitation: value),
        GroupNicknameField(
          controller: _nickname,
          defaultName:
              suggested ??
              (account == null ? '' : givenNames(account.fullName)),
          defaultLabel: suggested == null
              ? 'Mặc định'
              : '${value.inviterName} đặt',
        ),
        const Spacer(),
        MpButton(
          label: 'Chấp nhận',
          onPressed: _busy ? null : () => _answer(accept: true),
        ),
        MpButton(
          label: 'Từ chối',
          kind: MpButtonKind.ghost,
          size: MpButtonSize.m,
          onPressed: _busy ? null : () => _answer(accept: false),
        ),
      ],
    );
  }
}

class _AccessCard extends StatelessWidget {
  const _AccessCard({required this.invitation});

  final Invitation invitation;

  @override
  Widget build(BuildContext context) {
    final names = invitation.cameraNames;
    final watch = (MpIcons.eye, 'Xem camera: ${names.join(', ')}', true);
    final alerts = (
      MpIcons.bell,
      'Nhận báo cháy của ${invitation.cameraCount ?? names.length} camera này',
      true,
    );
    final lines = switch (invitation.role) {
      GroupRole.owner || GroupRole.manager => [
        watch,
        alerts,
        (MpIcons.check, 'Thêm/xoá camera, mời người', true),
      ],
      GroupRole.member => [
        watch,
        alerts,
        (MpIcons.close, 'Không thêm/xoá camera', false),
      ],
      GroupRole.alertsOnly => [
        alerts,
        (MpIcons.close, 'Không xem camera', false),
      ],
    };
    final c = context.mpColors;
    final t = context.mpText;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: c.bgCard,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 8,
        children: [
          for (final (icon, text, granted) in lines)
            Row(
              spacing: 10,
              children: [
                MpDuotoneIcon(
                  icon,
                  outline: granted ? c.brandAccent : c.textMuted,
                  accent: granted ? c.brandAccent : c.textMuted,
                  size: 18,
                ),
                Expanded(
                  child: Text(
                    text,
                    style: t.body.copyWith(
                      fontWeight: FontWeight.w500,
                      color: granted ? c.textPrimary : c.textSecondary,
                    ),
                  ),
                ),
              ],
            ),
        ],
      ),
    );
  }
}
