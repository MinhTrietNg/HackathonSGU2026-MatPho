library;

import 'package:flutter/material.dart';

import '../../core/widgets/mp_dialog.dart';
import '../../core/widgets/mp_illustration.dart';

const _illustration = MpIllustration(
  MpIllustrations.logout,
  size: MpDialog.illustrationSize,
);

Future<bool> confirmRemoveMember(BuildContext context, String name) =>
    showMpConfirm(
      context,
      MpConfirmDialog(
        illustration: _illustration,
        title: 'Xoá $name khỏi nhóm?',
        body: '$name sẽ không xem camera và không nhận báo cháy nữa.',
        confirmLabel: 'Xoá',
        cancelLabel: 'Huỷ',
      ),
    );

Future<bool> confirmLeaveGroup(BuildContext context, String groupName) =>
    showMpConfirm(
      context,
      MpConfirmDialog(
        illustration: _illustration,
        title: 'Rời $groupName?',
        body: 'Bạn sẽ không xem camera và không nhận báo cháy ở đây nữa.',
        confirmLabel: 'Rời nhóm',
        cancelLabel: 'Huỷ',
      ),
    );

Future<bool> confirmDeclineInvitation(
  BuildContext context,
  String inviterName,
) => showMpConfirm(
  context,
  MpConfirmDialog(
    illustration: _illustration,
    title: 'Từ chối lời mời?',
    body:
        '$inviterName sẽ thấy bạn đã từ chối. Muốn vào sau thì nhờ '
        '$inviterName mời lại.',
    confirmLabel: 'Từ chối',
    cancelLabel: 'Không',
  ),
);

Future<bool> confirmDissolveGroup(BuildContext context) => showMpConfirm(
  context,
  const MpConfirmDialog(
    illustration: _illustration,
    title: 'Giải tán nhóm này?',
    body:
        'Mọi người trong nhóm sẽ mất quyền xem camera và không nhận báo cháy '
        'nữa. Không hoàn tác được.',
    confirmLabel: 'Giải tán',
    cancelLabel: 'Huỷ',
  ),
);
