import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:xai_compress_authenticator/core/app_state.dart';
import 'package:xai_compress_authenticator/main.dart';
import 'package:xai_compress_authenticator/models/authenticator_account.dart';
import 'package:xai_compress_authenticator/screens/auth_screens.dart';
import 'package:xai_compress_authenticator/screens/home_screen.dart';
import 'package:xai_compress_authenticator/services/api_service.dart';
import 'package:xai_compress_authenticator/services/biometric_service.dart';
import 'package:xai_compress_authenticator/services/secure_account_store.dart';

const testUri =
    'otpauth://totp/XAI:test@example.com?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&issuer=XAI';

class MemoryStore extends SecureAccountStore {
  List<AuthenticatorAccount> stored = [];
  int writes = 0;
  @override
  Future<List<AuthenticatorAccount>> loadAccounts() async => stored;
  @override
  Future<void> saveAccounts(List<AuthenticatorAccount> accounts) async {
    writes++;
    stored = List.of(accounts);
  }
}

class FakeApi extends ApiService {
  bool requireMfa = false,
      loggedOut = false,
      resetRequested = false,
      resetDone = false;
  String verificationResult = 'ok';
  String? registeredName, registeredEmail, resetPasswordValue;
  int resetRequests = 0, enrollmentStarts = 0, enrollmentConfirms = 0;
  @override
  Future<void> register(
      {required String fullName,
      required String email,
      required String password}) async {
    registeredName = fullName;
    registeredEmail = email;
  }

  @override
  Future<LoginResult> login(
      {required String email,
      required String password,
      String? totpCode}) async {
    if (requireMfa && totpCode == null) {
      throw const ApiException('MFA_REQUIRED', 401);
    }
    if (requireMfa && totpCode != '123456') {
      throw const ApiException('invalid', 401);
    }
    accessToken = 'offline-test';
    return LoginResult(email: email, name: 'Test User');
  }

  @override
  Future<bool> confirmAccountVerification(String email, String code) async {
    if (verificationResult == 'expired') {
      throw const ApiException('expired', 410);
    }
    if (verificationResult == 'invalid' || code != '123456') {
      throw const ApiException('invalid', 400);
    }
    return true;
  }

  @override
  Future<void> sendAccountVerification(String email) async {}
  @override
  Future<Map<String, dynamic>> startAuthenticatorEnrollment() async {
    enrollmentStarts++;
    return {
      'enrollment_id': '0123456789abcdef0123456789abcdef',
      'otpauth_uri': testUri
    };
  }

  @override
  Future<bool> confirmAuthenticatorEnrollment(
      String enrollmentId, String code) async {
    enrollmentConfirms++;
    return code.length == 6;
  }

  @override
  Future<void> requestPasswordReset(String email) async {
    resetRequested = true;
    resetRequests++;
  }

  @override
  Future<String> verifyPasswordResetCode(String email, String code) async {
    if (verificationResult == 'expired') {
      throw const ApiException('expired', 410);
    }
    if (verificationResult == 'invalid') {
      throw const ApiException('invalid', 400);
    }
    return 'memory-only-reset-authorization-token-123456';
  }

  @override
  Future<void> resetPassword(String resetToken, String newPassword) async {
    resetDone = true;
    resetPasswordValue = newPassword;
  }

  @override
  Future<void> logout() async {
    loggedOut = true;
    accessToken = null;
  }
}

Future<AppState> mount(WidgetTester tester, FakeApi api, MemoryStore store,
    {Widget? screen, List<AuthenticatorAccount>? accounts}) async {
  final state = AppState(
      accountStore: store,
      biometricService: BiometricService(),
      apiService: api)
    ..loading = false
    ..unlocked = true
    ..accounts = accounts ?? [];
  addTearDown(state.dispose);
  await tester.pumpWidget(ChangeNotifierProvider.value(
      value: state,
      child: screen == null
          ? const XaiAuthenticatorApp()
          : MaterialApp(home: screen)));
  return state;
}

Future<void> enter(WidgetTester tester, String label, String value) async {
  await tester.enterText(find.byKey(ValueKey(label)), value);
  await tester.pump();
}

Future<void> tap(WidgetTester tester, String label) async {
  await tester.ensureVisible(find.text(label).last);
  await tester.tap(find.text(label).last);
  await tester.pump();
}

Future<void> completeRegistration(WidgetTester tester) async {
  await tap(tester, 'Create account');
  await tester.pumpAndSettle();
  await enter(tester, 'Full name', 'Test User');
  await enter(tester, 'Email', 'test@example.com');
  await enter(tester, 'Password', 'correct-password');
  await enter(tester, 'Confirm password', 'correct-password');
  await tap(tester, 'Create account');
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('landing is authentication first and create account navigates',
      (tester) async {
    await mount(tester, FakeApi(), MemoryStore());
    expect(find.text('Authentication, simplified'), findsOneWidget);
    expect(find.text('XAI Authenticator'), findsNothing);
    await tap(tester, 'Create account');
    await tester.pumpAndSettle();
    expect(find.text('Create account'), findsWidgets);
    expect(find.byKey(const ValueKey('Full name')), findsOneWidget);
  });

  testWidgets(
      'registration opens verification and successful verification enrolls securely',
      (tester) async {
    final api = FakeApi();
    final store = MemoryStore();
    await mount(tester, api, store);
    await completeRegistration(tester);
    expect(api.registeredName, 'Test User');
    expect(find.text('Verify your email'), findsOneWidget);
    await enter(tester, 'Verification code', '123456');
    await tap(tester, 'Verify email');
    await tester.pumpAndSettle();
    expect(find.text('Set up authenticator'), findsOneWidget);
    expect(api.enrollmentStarts, 1);
    expect(store.stored, hasLength(1));
    expect(store.writes, 1);
    await tap(tester, 'Activate authenticator');
    await tester.pumpAndSettle();
    expect(api.enrollmentConfirms, 1);
    expect(find.byKey(const ValueKey('totp-code')), findsOneWidget);
  });

  testWidgets('TOTP renders, refreshes at boundary, and copy uses current code',
      (tester) async {
    const account = AuthenticatorAccount(
        id: 'xai-1',
        issuer: 'XAI',
        accountName: 'test@example.com',
        secret: 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ',
        displayName: 'Test User');
    final state = await mount(tester, FakeApi(), MemoryStore(),
        screen: const HomeScreen(), accounts: [account]);
    state.now = DateTime.fromMillisecondsSinceEpoch(1700000000000);
    state.notifyListeners();
    await tester.pump();
    final first =
        (tester.widget<Text>(find.byKey(const ValueKey('totp-code')))).data;
    state.now = DateTime.fromMillisecondsSinceEpoch(1700000030000);
    state.notifyListeners();
    await tester.pump();
    final second =
        (tester.widget<Text>(find.byKey(const ValueKey('totp-code')))).data;
    expect(second, isNot(first));
    String? copied;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        copied = (call.arguments as Map)['text'] as String;
      }
      return null;
    });
    await tap(tester, 'Copy code');
    await tester.pump();
    expect(copied?.replaceAll(' ', ''), second?.replaceAll(' ', ''));
  });

  testWidgets('login requests MFA, accepts TOTP, and logout returns to landing',
      (tester) async {
    final api = FakeApi()..requireMfa = true;
    const account = AuthenticatorAccount(
        id: '1',
        issuer: 'XAI',
        accountName: 'test@example.com',
        secret: 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ');
    await mount(tester, api, MemoryStore(), accounts: [account]);
    await tap(tester, 'Login');
    await tester.pumpAndSettle();
    await enter(tester, 'Email', 'test@example.com');
    await enter(tester, 'Password', 'correct-password');
    await tap(tester, 'Login');
    await tester.pump();
    expect(find.text('Verify your identity'), findsOneWidget);
    await enter(tester, 'Authenticator code', '123456');
    await tap(tester, 'Verify and login');
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('totp-code')), findsOneWidget);
    await tester.tap(find.byTooltip('Logout'));
    await tester.pumpAndSettle();
    expect(api.loggedOut, isTrue);
    expect(find.text('Authentication, simplified'), findsOneWidget);
  });

  testWidgets(
      'forgot password is generic, validates codes/passwords, clears state and preserves MFA',
      (tester) async {
    final api = FakeApi();
    final store = MemoryStore()
      ..stored = [
        const AuthenticatorAccount(
            id: '1',
            issuer: 'XAI',
            accountName: 'test@example.com',
            secret: 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ')
      ];
    await mount(tester, api, store,
        screen: const LoginScreen(), accounts: store.stored);
    await tap(tester, 'Forgot password?');
    await tester.pumpAndSettle();
    expect(find.text('Reset password'), findsOneWidget);
    await enter(tester, 'Email', 'test@example.com');
    await tap(tester, 'Send reset code');
    await tester.pump();
    expect(api.resetRequested, isTrue);
    expect(find.textContaining('If the account is eligible'), findsOneWidget);
    expect(find.text('Resend in 60s'), findsOneWidget);
    await tester.pump(const Duration(seconds: 60));
    expect(find.text('Resend code'), findsOneWidget);
    await tap(tester, 'Resend code');
    await tester.pump();
    expect(api.resetRequests, 2);
    api.verificationResult = 'invalid';
    await enter(tester, 'Reset code', '111111');
    await tap(tester, 'Verify code');
    await tester.pump();
    expect(find.textContaining('invalid or expired'), findsOneWidget);
    api.verificationResult = 'ok';
    await enter(tester, 'Reset code', '123456');
    await tap(tester, 'Verify code');
    await tester.pump();
    await enter(tester, 'New password', 'new-password-123');
    await enter(tester, 'Confirm new password', 'different-password');
    await tap(tester, 'Reset password');
    await tester.pump();
    expect(find.text('Passwords do not match.'), findsOneWidget);
    await enter(tester, 'Confirm new password', 'new-password-123');
    await tap(tester, 'Reset password');
    await tester.pump();
    expect(api.resetDone, isTrue);
    expect(store.stored, hasLength(1));
    expect(store.writes, 0);
    expect(find.text('Return to Login'), findsOneWidget);
    await tap(tester, 'Return to Login');
    await tester.pumpAndSettle();
    expect(find.text('Welcome back'), findsOneWidget);
  });

  testWidgets('expired reset code has dedicated handling', (tester) async {
    final api = FakeApi()..verificationResult = 'expired';
    await mount(tester, api, MemoryStore(),
        screen: const ForgotPasswordScreen());
    await enter(tester, 'Email', 'test@example.com');
    await tap(tester, 'Send reset code');
    await tester.pump();
    await enter(tester, 'Reset code', '123456');
    await tap(tester, 'Verify code');
    await tester.pump();
    expect(find.text('This reset code expired. Request a new code.'),
        findsOneWidget);
  });

  testWidgets('auth landing remains scroll-safe on a small scaled display',
      (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    await mount(tester, FakeApi(), MemoryStore(),
        screen: const MediaQuery(
            data: MediaQueryData(textScaler: TextScaler.linear(1.3)),
            child: LandingScreen()));
    expect(find.text('Authentication, simplified'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
