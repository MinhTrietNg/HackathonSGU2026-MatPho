library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_button.dart';
import '../../core/widgets/mp_duotone_icon.dart';
import '../../core/widgets/mp_header.dart';
import '../../core/widgets/mp_page.dart';
import '../../core/widgets/mp_text_field.dart';
import 'group_routes.dart';
import 'group_state.dart';
import 'group_widgets.dart';

class CreateGroupScreen extends ConsumerStatefulWidget {
  const CreateGroupScreen({
    super.key,
    this.initialName,
    this.previewFocused = false,
  });

  final String? initialName;

  final bool previewFocused;

  @override
  ConsumerState<CreateGroupScreen> createState() => _CreateGroupScreenState();
}

class _CreateGroupScreenState extends ConsumerState<CreateGroupScreen> {
  late final _name = TextEditingController(text: widget.initialName);
  final _nickname = TextEditingController();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _name.addListener(_changed);
  }

  @override
  void dispose() {
    _name.dispose();
    _nickname.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  Future<void> _create() async {
    setState(() => _busy = true);
    final nickname = _nickname.text.trim();
    final account = ref.read(groupAccountProvider);
    final done = await runGroupAction(context, () async {
      await ref
          .read(groupActionsProvider)
          .createGroup(
            name: _name.text.trim(),
            myNickname: nickname.isEmpty ? account?.fullName : nickname,
          );
    });
    if (!mounted) return;
    setState(() => _busy = false);
    if (done) context.pushReplacement(GroupRoutes.members);
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    final account = ref.watch(groupAccountProvider);

    return MpPage(
      header: MpHeader.back(title: 'Tạo nhóm', onBack: () => context.pop()),
      headerBottom: 14,
      gap: 14,
      children: [
        MpTextField(
          label: 'Tên nhóm',
          icon: MpIcons.edit,
          controller: _name,
          textInputAction: TextInputAction.next,
          state: widget.previewFocused ? MpFieldState.focused : null,
        ),
        GroupNicknameField(
          controller: _nickname,
          defaultName: account == null ? '' : givenNames(account.fullName),
        ),
        Text(
          'Để trống sẽ dùng tên tài khoản.',
          style: t.caption.copyWith(
            fontWeight: FontWeight.w500,
            color: c.textMuted,
          ),
        ),
        const Spacer(),
        MpButton(
          label: 'Tạo nhóm',
          icon: MpIcons.plus,
          onPressed: _busy || _name.text.trim().isEmpty ? null : _create,
        ),
      ],
    );
  }
}
