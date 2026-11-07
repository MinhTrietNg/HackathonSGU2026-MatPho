package com.matpho.mat_pho

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log

object FireAlarmSirenPlayer {
    private const val TAG = "FireAlarmSirenPlayer"
    private var mediaPlayer: MediaPlayer? = null
    private var savedAlarmVolume: Int? = null
    private var savedMusicVolume: Int? = null

    @Synchronized
    fun startSiren(context: Context) {
        val appCtx = context.applicationContext
        try {
            val audioManager = appCtx.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            if (audioManager != null) {
                if (savedAlarmVolume == null) {
                    savedAlarmVolume = audioManager.getStreamVolume(AudioManager.STREAM_ALARM)
                }
                if (savedMusicVolume == null) {
                    savedMusicVolume = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC)
                }
                try {
                    val maxAlarm = audioManager.getStreamMaxVolume(AudioManager.STREAM_ALARM)
                    audioManager.setStreamVolume(AudioManager.STREAM_ALARM, maxAlarm, 0)
                } catch (e: Throwable) {
                    Log.w(TAG, "Could not force max STREAM_ALARM volume: ${e.message}")
                }
                try {
                    val maxMusic = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
                    audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, maxMusic, 0)
                } catch (e: Throwable) {
                    Log.w(TAG, "Could not force max STREAM_MUSIC volume: ${e.message}")
                }
            }

            stopMediaPlayerOnly()

            val afd = appCtx.resources.openRawResourceFd(R.raw.fire_alarm_siren)
            val player = MediaPlayer()
            val attrs = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .setFlags(AudioAttributes.FLAG_AUDIBILITY_ENFORCED)
                .build()
            player.setAudioAttributes(attrs)
            player.setDataSource(afd.fileDescriptor, afd.startOffset, afd.length)
            afd.close()
            player.isLooping = true
            player.setVolume(1.0f, 1.0f)
            player.prepare()
            player.start()
            mediaPlayer = player
            Log.i(TAG, "Started continuous fire alarm siren at MAX volume (USAGE_ALARM)")
        } catch (e: Throwable) {
            Log.e(TAG, "Failed to start fire alarm siren: ${e.message}", e)
        }

        try {
            val vibrator = getVibrator(appCtx)
            val pattern = longArrayOf(0, 500, 200, 500, 200, 500, 200, 500, 200, 1000)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val attrs = AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .build()
                vibrator?.vibrate(VibrationEffect.createWaveform(pattern, 0), attrs)
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(pattern, 0)
            }
        } catch (e: Throwable) {
            Log.w(TAG, "Failed to start continuous vibration: ${e.message}")
        }
    }

    @Synchronized
    fun stopSiren(context: Context) {
        val appCtx = context.applicationContext
        stopMediaPlayerOnly()

        try {
            getVibrator(appCtx)?.cancel()
        } catch (_: Throwable) {
        }

        try {
            val audioManager = appCtx.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            if (audioManager != null) {
                savedAlarmVolume?.let {
                    try {
                        audioManager.setStreamVolume(AudioManager.STREAM_ALARM, it, 0)
                    } catch (_: Throwable) {
                    }
                }
                savedMusicVolume?.let {
                    try {
                        audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, it, 0)
                    } catch (_: Throwable) {
                    }
                }
            }
        } finally {
            savedAlarmVolume = null
            savedMusicVolume = null
        }
        Log.i(TAG, "Stopped fire alarm siren and restored volume")
    }

    private fun stopMediaPlayerOnly() {
        try {
            mediaPlayer?.let {
                if (it.isPlaying) {
                    it.stop()
                }
                it.release()
            }
        } catch (_: Throwable) {
        } finally {
            mediaPlayer = null
        }
    }

    private fun getVibrator(context: Context): Vibrator? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val vm = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
            vm?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        }
    }
}

class FireAlarmSirenReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent == null) return
        val extras = intent.extras ?: return
        val type = extras.getString("type") ?: extras.getString("gcm.notification.type") ?: ""
        if (type == "FIRE_ALERT") {
            FireAlarmSirenPlayer.startSiren(context)
        } else if (type == "FIRE_ALERT_UPDATED") {
            FireAlarmSirenPlayer.stopSiren(context)
        }
    }
}
