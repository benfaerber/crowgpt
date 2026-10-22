package expo.modules.rawaudio

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder

/**
 * Keeps the microphone available while the app is not on screen.
 *
 * It records nothing itself. Android's rule is about whether the *app* has a
 * microphone-type foreground service running, not about which component reads
 * the audio — so [WavRecorder] keeps doing that, and this exists only to hold
 * the permission open. Making the service own the recorder would move the ring
 * buffer across a process boundary for no gain.
 *
 * The notification is mandatory and cannot be hidden. That is the right trade:
 * a phone holding an open microphone in a pocket should be impossible to forget
 * about, and the text says plainly what is and is not being saved.
 */
class ListeningService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    /**
     * Swiped out of recents: let go of the microphone.
     *
     * A foreground service survives its task being removed — that is the whole
     * point of one — so without this the app disappeared from the switcher and
     * kept the mic open behind it. Somebody who has just dismissed an app has
     * unambiguously finished with it, and "it is still recording, you simply
     * cannot see it" is not a defensible reading of that gesture.
     *
     * Stopping the service is not enough on its own: it holds the *permission*,
     * not the audio. The recorder has to be told as well, which is what the
     * callback below is for.
     */
    override fun onTaskRemoved(rootIntent: Intent?) {
        onStopRequested?.invoke()
        stopSelf()
        super.onTaskRemoved(rootIntent)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        ensureChannel()
        // Always, before anything else can go wrong. `startForegroundService`
        // makes a promise the system enforces: if this never calls
        // `startForeground`, it kills the app — which it did, with
        // ForegroundServiceDidNotStartInTimeException, when a start was
        // followed by a stop before this method ever ran. A stop that arrives
        // early is honoured below instead, after the promise is kept.
        val builder = Notification.Builder(this, CHANNEL)
            .setContentTitle(DEFAULT_TITLE)
            .setContentText(DEFAULT_TEXT)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            // The text, not "contents hidden", on a locked phone. "Microphone
            // is open" is the one line this notification exists to show, and
            // the lock screen is the one place it is read — a pocketed phone
            // is locked by definition. Nothing sensitive is in it.
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setContentIntent(openApp())
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            // Android 12 holds a foreground service notification back for ten
            // seconds when the app that started it is on screen, on the
            // reasonable theory that most of them are noise the user can
            // already see the cause of. This one is the exception: it is the
            // only thing that says a microphone is open, and a phone that goes
            // into a pocket inside that ten seconds is exactly the case it
            // exists for. Deferring it made it look like it did not always
            // appear, because it did not.
            builder.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE)
        }
        val notification = builder.build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(ID, notification)
        }
        // A stop that arrived while this was still being delivered. Honoured
        // now rather than dropped: the alternative is a notification for a
        // microphone nobody is holding.
        if (stopRequested) {
            stopRequested = false
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
        // Not sticky: if Android kills this, the ring buffer died with the
        // process and restarting the service alone would hold the microphone
        // open while recording nothing.
        return START_NOT_STICKY
    }

    private fun openApp(): PendingIntent? {
        val launch = packageManager.getLaunchIntentForPackage(packageName) ?: return null
        return PendingIntent.getActivity(
            this, 0, launch,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        // The first channel was IMPORTANCE_LOW, which recent Android files
        // under "silent" — and the lock screen and Always-On Display both hide
        // silent notifications. Pocket listening is only used locked, so the
        // notification was invisible in exactly the situation it was built
        // for. A channel's importance belongs to the user once it exists and
        // cannot be raised in code, hence the new id; the old channel is
        // deleted so it does not sit in system settings as a duplicate.
        manager.deleteNotificationChannel(LEGACY_CHANNEL)
        if (manager.getNotificationChannel(CHANNEL) != null) return
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL,
                "Listening",
                // Default importance is what earns a place on the lock screen.
                // The noise that normally comes with it is stripped below —
                // visible without buzzing every time the mic opens.
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = "Shown whenever CrowGPT is holding the microphone open."
                setShowBadge(false)
                setSound(null, null)
                enableVibration(false)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            },
        )
    }

    companion object {
        private const val CHANNEL = "cawtalker.listening.v2"
        private const val LEGACY_CHANNEL = "cawtalker.listening"
        private const val ID = 1

        /**
         * What the notification says when nothing but the buffer is running.
         * Constants because idle mode borrows the notification and must be
         * able to hand it back saying exactly what it said before — "nothing
         * is saved until you press Record" is a promise, and idle mode is
         * the one state in which it would be a lie.
         */
        const val DEFAULT_TITLE = "Listening for crows"
        const val DEFAULT_TEXT =
            "Microphone is open. Nothing is saved until you press Record."

        /**
         * Re-say what the held microphone means, without touching the service.
         *
         * The notification is the app's one always-visible surface, and while
         * idle mode is armed its default text is untrue. Same id, same
         * channel: the system treats it as the ongoing notification changing
         * its words, not a second one arriving.
         */
        fun update(context: Context, title: String, text: String) {
            if (!running) return
            val manager =
                context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
            val builder = Notification.Builder(context, CHANNEL)
                .setContentTitle(title)
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setOngoing(true)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
            if (launch != null) {
                builder.setContentIntent(
                    PendingIntent.getActivity(
                        context, 0, launch,
                        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
                    ),
                )
            }
            manager.notify(ID, builder.build())
        }

        /**
         * How the service asks the recorder to let go.
         *
         * Set by the module when listening starts and cleared when it stops, so
         * nothing outlives the session that installed it. A plain callback
         * rather than a binding: the service and the recorder live in the same
         * process, and a Binder here would be ceremony around a function call.
         */
        @Volatile
        var onStopRequested: (() -> Unit)? = null

        /** Whether the service is currently holding the microphone permission. */
        @Volatile
        var running = false
            private set

        /**
         * Set when a stop arrives before the service has been delivered.
         *
         * `stopService` on a service whose `onStartCommand` has not run yet
         * cancels the delivery, leaving the system waiting for a
         * `startForeground` that will never come — and then killing the app for
         * it. The service reads this once it does start and stands down.
         */
        @Volatile
        private var stopRequested = false

        fun start(context: Context) {
            running = true
            stopRequested = false
            val intent = Intent(context, ListeningService::class.java)
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            running = false
            stopRequested = true
            context.stopService(Intent(context, ListeningService::class.java))
        }
    }
}
