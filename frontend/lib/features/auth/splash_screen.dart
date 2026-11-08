library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../core/theme/theme.dart';
import '../../core/widgets/mp_brand.dart';
import 'auth_session.dart';

class SplashScreen extends ConsumerStatefulWidget {
  const SplashScreen({super.key, this.onSessionRestored});

  final ValueChanged<AuthSession>? onSessionRestored;

  @override
  ConsumerState<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends ConsumerState<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    try {
      final session = await ref.read(authSessionProvider.notifier).restore();
      if (mounted) widget.onSessionRestored?.call(session);
    } catch (_) {
      if (mounted) widget.onSessionRestored?.call(const SignedOut());
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return Scaffold(
      backgroundColor: c.bgBase,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
          child: Semantics(
            label: 'Mắt Phố',
            container: true,
            child: SizedBox(
              width: double.infinity,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                spacing: 18,
                children: [
                  SvgPicture.asset(
                    MpBrand.logoMark,
                    width: 112,
                    height: 112,
                    excludeFromSemantics: true,
                  ),
                  Text(
                    'MẮT PHỐ',
                    style: t.display.copyWith(
                      fontSize: 34,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 1.36,
                      color: c.textPrimary,
                    ),
                  ),
                  Text(
                    'CANH CHÁY BẰNG CAMERA',
                    style: t.mono.copyWith(
                      fontWeight: FontWeight.w600,
                      color: c.brandAccentFg,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
