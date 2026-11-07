package com.matpho.mat_pho

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

// Fire alert flow: a fire notification (tap or full-screen intent) opens F2
// over the lock screen; once the app leaves the screen, it needs an unlock again.
class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.matpho.mat_pho/siren"
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "start" -> {
                    FireAlarmSirenPlayer.startSiren(applicationContext)
                    result.success(true)
                }
                "stop" -> {
                    FireAlarmSirenPlayer.stopSiren(applicationContext)
                    result.success(true)
                }
                else -> result.notImplemented()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        showOverLockScreen(isFireAlert(intent))
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        showOverLockScreen(isFireAlert(intent))
    }

    override fun onStop() {
        super.onStop()
        showOverLockScreen(false)
    }

    private fun isFireAlert(intent: Intent?) = intent?.action == "SELECT_NOTIFICATION"

    private fun showOverLockScreen(show: Boolean) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(show)
            setTurnScreenOn(show)
        } else {
            @Suppress("DEPRECATION")
            val flags = WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
            if (show) window.addFlags(flags) else window.clearFlags(flags)
        }
    }
}
