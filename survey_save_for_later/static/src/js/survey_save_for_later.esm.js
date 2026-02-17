/* @odoo-module */
/* eslint-disable sort-imports */

import publicWidget from "@web/legacy/js/public/public_widget";
import {rpc} from "@web/core/network/rpc";
import {_t} from "@web/core/l10n/translation";

/**
 * Survey Save For Later Widget
 *
 * Extends the SurveyFormWidget to add "Save for Later" functionality.
 * This widget handles:
 * - Collecting current form data
 * - Sending it to the save_for_later controller
 * - Displaying a confirmation modal with resume link
 */
export const SurveySaveForLaterWidget = publicWidget.Widget.extend({
    selector: ".o_survey_form",

    events: {
        "click .o_survey_save_for_later_btn": "_onSaveForLaterClick",
        "click #o_copy_resume_url": "_onCopyResumeUrl",
    },

    /**
     * @override
     */
    async start() {
        this.$modal = null;
        this.$resumeUrlInput = null;
        this.$button = null;
        await this._super(...arguments);
        // Initialize modal and button if they exist in the DOM
        this.$modal = $("#SaveForLaterModal");
        this.$resumeUrlInput = $("#o_save_for_later_resume_url");
        this.$button = $(".o_survey_save_for_later_btn");
    },

    // --------------------------------------------------------------------------
    // Handlers
    // --------------------------------------------------------------------------

    /**
     * Handle the Save for Later button click.
     * @param {Event} ev
     */
    async _onSaveForLaterClick(ev) {
        ev.preventDefault();
        const $button = $(ev.currentTarget);

        const surveyToken = this.$("form").data("surveyToken");
        const answerToken = this.$("form").data("answerToken");
        const formData = this._collectFormData();

        // Disable button and show loading
        $button.prop("disabled", true);
        const originalText = $button.text();
        $button.text(_t("Saving..."));

        try {
            const result = await rpc(
                `/survey/save_for_later/${surveyToken}/${answerToken}`,
                formData
            );
            if (result.error) {
                this._showNotification(
                    _t("An error occurred while saving. Please try again.")
                );
            } else if (result.success) {
                this._showSaveForLaterModal(result);
            }
        } catch {
            this._showNotification(
                _t("An error occurred while saving. Please try again.")
            );
        } finally {
            $button.prop("disabled", false);
            $button.text(originalText);
        }
    },

    /**
     * Handle the copy resume URL button click.
     * @param {Event} ev
     */
    async _onCopyResumeUrl(ev) {
        ev.preventDefault();
        const $button = $(ev.currentTarget);
        const $input = this.$resumeUrlInput;

        if (!$input || !$input.length) {
            return;
        }

        $input.select();
        const originalText = $button.text();

        if (navigator.clipboard && navigator.clipboard.writeText) {
            try {
                await navigator.clipboard.writeText($input.val());
                $button.text(_t("Copied!"));
            } catch {
                // Clipboard failed, text is already selected
                $button.text(_t("Selected!"));
            }
        } else {
            // Fallback for older browsers - text is already selected
            $button.text(_t("Selected!"));
        }

        setTimeout(() => {
            $button.text(originalText);
        }, 2000);
    },

    // --------------------------------------------------------------------------
    // Private
    // --------------------------------------------------------------------------

    /**
     * Collect current form data from the survey using native FormData API.
     * @returns {Object} form data as a plain object
     */
    _collectFormData() {
        const $form = this.$("form");
        const formData = new FormData($form[0]);
        const data = {};

        formData.forEach((value, key) => {
            // Handle multiple values for the same key (e.g., checkboxes)
            if (key in data) {
                if (Array.isArray(data[key])) {
                    data[key].push(value);
                } else {
                    data[key] = [data[key], value];
                }
            } else {
                data[key] = value;
            }
        });

        return data;
    },

    /**
     * Show the save for later confirmation modal.
     * @param {Object} result - the result from the save_for_later controller
     */
    _showSaveForLaterModal(result) {
        if (!this.$modal.length) {
            // Fallback: use alert if modal is not available
            this._showNotification(
                _t("Your progress has been saved. Resume URL: ") + result.resume_url
            );
            return;
        }

        // Set resume URL
        if (this.$resumeUrlInput.length) {
            this.$resumeUrlInput.val(result.resume_url);
        }

        // Show/hide email alert
        const $emailAlert = this.$modal.find("#o_email_sent_alert");
        if ($emailAlert.length) {
            if (result.email_sent) {
                $emailAlert.removeClass("d-none");
            } else {
                $emailAlert.addClass("d-none");
            }
        }

        this.$modal.modal("show");
    },

    /**
     * Show a notification to the user.
     * @param {String} message - the notification message
     */
    _showNotification(message) {
        // eslint-disable-next-line no-alert
        alert(message);
    },
});

publicWidget.registry.SurveySaveForLaterWidget = SurveySaveForLaterWidget;
