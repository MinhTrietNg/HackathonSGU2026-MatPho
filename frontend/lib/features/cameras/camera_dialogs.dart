library;

import 'package:flutter/material.dart';

import '../../core/widgets/mp_dialog.dart';
import '../../core/widgets/mp_illustration.dart';

const _illustration = MpIllustration(
  MpIllustrations.delete,
  size: MpDialog.illustrationSize,
);

// I17: a deleted camera also loses its RTSP stream on the server, but sits
// in the 30-day trash (I18) until then.
Future<bool> confirmDeleteCamera(BuildContext context, String name) =>
    showMpConfirm(
      context,
      MpConfirmDialog(
        illustration: _illustration,
        title: 'Xoá camera $name?',
        body:
            'Đường dẫn RTSP sẽ bị gỡ, AI ngừng quét khu này. Bạn có 30 ngày '
            'để khôi phục trong Cài đặt › Camera đã xoá.',
        confirmLabel: 'Xoá',
        cancelLabel: 'Huỷ',
      ),
    );

// I21: the camera keeps its name, area, history and member access.
Future<bool> confirmRemoveRtsp(BuildContext context, String name) =>
    showMpConfirm(
      context,
      MpConfirmDialog(
        illustration: _illustration,
        title: 'Gỡ đường dẫn RTSP của $name?',
        body:
            'AI ngừng quét camera này. Tên, khu vực, lịch sử và quyền xem giữ '
            'nguyên; thêm lại RTSP bất cứ lúc nào.',
        confirmLabel: 'Gỡ RTSP',
        cancelLabel: 'Huỷ',
      ),
    );

// I19
Future<bool> confirmDeleteCameraForever(BuildContext context, String name) =>
    showMpConfirm(
      context,
      MpConfirmDialog(
        illustration: _illustration,
        title: 'Xoá hẳn camera $name?',
        body: 'Camera bị xoá ngay và không khôi phục được.',
        confirmLabel: 'Xoá hẳn',
        cancelLabel: 'Huỷ',
      ),
    );
