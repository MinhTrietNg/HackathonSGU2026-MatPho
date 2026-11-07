import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:mat_pho/core/theme/theme.dart';
import 'gallery_registry.dart';

class GalleryScreen extends StatelessWidget {
  const GalleryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final c = context.mpColors;
    final t = context.mpText;
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
          children: [
            Text('Gallery', style: t.title),
            for (final group in galleryGroups) ...[
              Padding(
                padding: const EdgeInsets.only(top: 20, bottom: 8),
                child: Text(
                  group.name.toUpperCase(),
                  style: t.caption.copyWith(color: c.textMuted),
                ),
              ),
              for (final entry in group.entries)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: SizedBox(
                    width: 40,
                    child: Text(
                      entry.code,
                      style: t.mono.copyWith(color: c.brandAccentFg),
                    ),
                  ),
                  title: Text(entry.title, style: t.body),
                  onTap: () => context.push('/gallery/${entry.code}'),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class GalleryEntryScreen extends StatelessWidget {
  const GalleryEntryScreen({super.key, required this.code});

  final String code;

  @override
  Widget build(BuildContext context) {
    final entry = findGalleryEntry(code);
    if (entry == null) {
      return Scaffold(
        body: Center(
          child: Text('Unknown entry: $code', style: context.mpText.body),
        ),
      );
    }
    return entry.builder(context);
  }
}
