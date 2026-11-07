import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mat_pho/data/remote/core/remote_providers.dart';
import 'package:mat_pho/data/session/auth_token_source.dart';
import 'package:mat_pho/data/session/push_token_source.dart';
import 'package:mat_pho/data/session/session_store.dart';

void main() {
  group('SecureSessionStore', () {
    const user = <String, Object?>{
      'user_id': 'usr_abc123',
      'phone_number': '+84912345678',
      'full_name': 'Nguyễn Minh Anh',
      'loud_when_silent': true,
      'personal_group_id': 'grp_personal_usr_abc123',
    };

    setUp(() => FlutterSecureStorage.setMockInitialValues({}));

    test('save, read, clear', () async {
      final store = SecureSessionStore();
      expect(await store.read(), isNull);
      await store.save(user);
      expect(await store.read(), user);
      await store.clear();
      expect(await store.read(), isNull);
    });

    test('unreadable data reads as signed out', () async {
      FlutterSecureStorage.setMockInitialValues({'mp.session.user': '{oops'});
      expect(await SecureSessionStore().read(), isNull);
    });
  });

  test('NoPushTokenSource has no token', () async {
    const source = NoPushTokenSource();
    expect(await source.token(), isNull);
    expect(await source.onTokenRefresh.isEmpty, isTrue);
  });

  test('remote providers build without Firebase, storage or URLs', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    expect(container.read(apiClientProvider), isNotNull);
    expect(container.read(wsClientProvider), isNotNull);
    expect(container.read(sessionStoreProvider), isA<SecureSessionStore>());
    expect(
      container.read(authTokenSourceProvider),
      isA<FirebaseAuthTokenSource>(),
    );
    expect(container.read(pushTokenSourceProvider), isA<NoPushTokenSource>());
    expect(container.read(sessionExpiredProvider), isA<Stream<void>>());
  });
}
