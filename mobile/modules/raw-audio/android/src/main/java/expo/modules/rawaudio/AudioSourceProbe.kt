package expo.modules.rawaudio

import android.content.Context
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.AudioEffect
import android.media.audiofx.AutomaticGainControl
import android.media.audiofx.NoiseSuppressor
import android.os.Build
import android.util.Log
import org.json.JSONObject
import java.io.File
import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.sqrt

/**
 * Diagnostic: opens every candidate mic source in turn and reports what the OS
 * actually gave us, rather than what a capability flag claims.
 *
 * The interesting part is [AudioManager.getActiveRecordingConfigurations]. While
 * a recording is live it reports the source the audio policy really selected and
 * the effects attached to the record path — so "is AGC on?" becomes a reading
 * instead of an inference from the noise floor.
 *
 * Nothing here runs on the capture path; [WavRecorder] is untouched by it.
 */
class AudioSourceProbe(private val context: Context) {

    private data class Candidate(val label: String, val source: Int)

    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private val candidates = listOf(
        Candidate("UNPROCESSED", MediaRecorder.AudioSource.UNPROCESSED),
        Candidate("VOICE_RECOGNITION", MediaRecorder.AudioSource.VOICE_RECOGNITION),
        Candidate("MIC", MediaRecorder.AudioSource.MIC),
        Candidate("CAMCORDER", MediaRecorder.AudioSource.CAMCORDER),
        Candidate("VOICE_COMMUNICATION", MediaRecorder.AudioSource.VOICE_COMMUNICATION),
    )

    fun run(sampleRate: Int, millisPerSource: Int, keepAudio: Boolean): Map<String, Any?> {
        val report: Map<String, Any?> = mapOf(
            "device" to "${Build.MANUFACTURER} ${Build.MODEL}",
            "androidRelease" to Build.VERSION.RELEASE,
            "sdkInt" to Build.VERSION.SDK_INT,
            "propertyRaw" to propertyRaw(),
            "propertyIsNull" to (propertyRaw() == null),
            "effectsAvailable" to mapOf(
                "agc" to AutomaticGainControl.isAvailable(),
                "ns" to NoiseSuppressor.isAvailable(),
                "aec" to AcousticEchoCanceler.isAvailable(),
            ),
            "sources" to candidates.map { probe(it, sampleRate, millisPerSource, keepAudio) },
        )
        Log.i(TAG, report.toString())
        File(context.cacheDir, REPORT_NAME).writeText(JSONObject(report).toString(2))
        return report
    }

    private fun propertyRaw(): String? =
        audioManager.getProperty(AudioManager.PROPERTY_SUPPORT_AUDIO_SOURCE_UNPROCESSED)

    private fun probe(
        candidate: Candidate,
        sampleRate: Int,
        millisPerSource: Int,
        keepAudio: Boolean,
    ): Map<String, Any?> {
        val result = mutableMapOf<String, Any?>(
            "label" to candidate.label,
            "requestedSource" to candidate.source,
        )

        val channelConfig = AudioFormat.CHANNEL_IN_MONO
        val encoding = AudioFormat.ENCODING_PCM_16BIT
        val minBuf = AudioRecord.getMinBufferSize(sampleRate, channelConfig, encoding)
        if (minBuf <= 0) {
            result["opened"] = false
            result["error"] = "getMinBufferSize returned $minBuf"
            return result
        }

        val bufSize = maxOf(minBuf, sampleRate / 4)
        val record = try {
            AudioRecord(candidate.source, sampleRate, channelConfig, encoding, bufSize)
        } catch (e: Exception) {
            result["opened"] = false
            result["error"] = "constructor threw: ${e.message}"
            return result
        }

        result["state"] = if (record.state == AudioRecord.STATE_INITIALIZED) {
            "INITIALIZED"
        } else {
            "UNINITIALIZED"
        }
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            result["opened"] = false
            return result
        }
        result["opened"] = true
        result["audioSessionId"] = record.audioSessionId

        val wav = if (keepAudio) {
            WavFile(File(context.cacheDir, "probe_${candidate.label}.wav"), sampleRate)
        } else {
            null
        }

        try {
            record.startRecording()
            result["recordingState"] =
                if (record.recordingState == AudioRecord.RECORDSTATE_RECORDING) "RECORDING" else "STOPPED"

            val buffer = ByteArray(bufSize)
            val deadline = System.nanoTime() + millisPerSource * 1_000_000L
            var peak = 0
            var sumSquares = 0.0
            var samples = 0L
            var configuration: Map<String, Any?>? = null

            while (System.nanoTime() < deadline) {
                val read = record.read(buffer, 0, buffer.size)
                if (read <= 0) continue
                wav?.write(buffer, read)
                var i = 0
                while (i + 1 < read) {
                    val sample = ((buffer[i].toInt() and 0xff) or (buffer[i + 1].toInt() shl 8)).toShort().toInt()
                    if (abs(sample) > peak) peak = abs(sample)
                    sumSquares += sample.toDouble() * sample.toDouble()
                    samples++
                    i += 2
                }
                if (configuration == null) configuration = readConfiguration(record.audioSessionId)
            }

            result["configuration"] = configuration ?: readConfiguration(record.audioSessionId)
            result["peakDbfs"] = dbfs(peak.toDouble())
            result["rmsDbfs"] = dbfs(if (samples > 0) sqrt(sumSquares / samples) else 0.0)
            result["framesRead"] = samples
            result["effectControl"] = probeEffectControl(record.audioSessionId)
            result["path"] = wav?.let { File(context.cacheDir, "probe_${candidate.label}.wav").absolutePath }
        } catch (e: Exception) {
            result["error"] = "${e.javaClass.simpleName}: ${e.message}"
        } finally {
            try {
                record.stop()
            } catch (_: Exception) {
            }
            record.release()
            wav?.close()
        }
        return result
    }

    /**
     * What the audio policy actually did with our request, read back live.
     * A non-privileged app only sees its own recording configurations, which is
     * exactly the one we want.
     */
    private fun readConfiguration(sessionId: Int): Map<String, Any?>? {
        val configuration = audioManager.activeRecordingConfigurations
            .firstOrNull { it.clientAudioSessionId == sessionId }
            ?: return null

        val report = mutableMapOf<String, Any?>(
            "clientAudioSource" to configuration.clientAudioSource,
            "clientAudioSourceLabel" to RecordPathInspector.sourceLabel(configuration.clientAudioSource),
            "device" to configuration.audioDevice?.type,
            "deviceLabel" to RecordPathInspector.deviceLabel(configuration.audioDevice?.type),
        )
        report["audioSource"] = try {
            configuration.audioSource
        } catch (e: Throwable) {
            "unavailable: ${e.javaClass.simpleName}"
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            report["effects"] = describe(configuration.effects)
            report["clientEffects"] = describe(configuration.clientEffects)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            report["clientSilenced"] = configuration.isClientSilenced
        }
        return report
    }

    private fun describe(descriptors: List<AudioEffect.Descriptor>?): List<Map<String, String?>> =
        descriptors.orEmpty().map {
            mapOf(
                "type" to RecordPathInspector.effectLabel(it.type),
                "name" to it.name,
                "implementor" to it.implementor,
                "mode" to it.connectMode,
            )
        }

    /**
     * Can we turn the speech processing off ourselves? Each effect is attached to
     * the live session, its incoming state recorded, then disabled and released.
     */
    private fun probeEffectControl(sessionId: Int): Map<String, Any?> = mapOf(
        "agc" to control("agc", AutomaticGainControl.isAvailable()) {
            AutomaticGainControl.create(sessionId)
        },
        "ns" to control("ns", NoiseSuppressor.isAvailable()) {
            NoiseSuppressor.create(sessionId)
        },
        "aec" to control("aec", AcousticEchoCanceler.isAvailable()) {
            AcousticEchoCanceler.create(sessionId)
        },
    )

    private fun control(
        label: String,
        available: Boolean,
        create: () -> AudioEffect?,
    ): Map<String, Any?> {
        if (!available) return mapOf("available" to false)
        val effect = try {
            create()
        } catch (e: Exception) {
            return mapOf("available" to true, "error" to "${e.javaClass.simpleName}: ${e.message}")
        } ?: return mapOf("available" to true, "created" to false)

        return try {
            val enabledOnAttach = effect.enabled
            val disableResult = effect.setEnabled(false)
            mapOf(
                "available" to true,
                "created" to true,
                "hasControl" to effect.hasControl(),
                "enabledOnAttach" to enabledOnAttach,
                "disableOk" to (disableResult == AudioEffect.SUCCESS),
                "enabledAfterDisable" to effect.enabled,
            )
        } catch (e: Exception) {
            mapOf("available" to true, "created" to true, "error" to "${e.javaClass.simpleName}: ${e.message}")
        } finally {
            effect.release()
        }
    }

    private fun dbfs(amplitude: Double): Double =
        if (amplitude <= 0) -120.0 else 20 * log10(amplitude / Short.MAX_VALUE)

    companion object {
        const val TAG = "RawAudioProbe"
        const val REPORT_NAME = "probe_report.json"
    }
}
