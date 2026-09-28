/* Live input sampling, on the CPU/main thread only. System actions remain in
 * the event loop: a JOYP read must never reset or load the machine mid-opcode. */
static void rr_gb_sample_input(GBContext* ctx, bool force) {
    if (g_benchmark_mode || g_script_count || g_show_menu || g_app_suspended || !g_window)
        return;
    const uint64_t now = SDL_GetPerformanceCounter();
    const uint64_t frequency = SDL_GetPerformanceFrequency();
    const uint64_t interval = frequency / 1000u ? frequency / 1000u : 1u;
    if (!force && g_rr_input_sample_time && now - g_rr_input_sample_time < interval)
        return;
    SDL_PumpEvents();
    const uint8_t previous_dpad = g_joypad_dpad;
    const uint8_t previous_buttons = g_joypad_buttons;
    const Uint8* keys = SDL_GetKeyboardState(NULL);
    const bool focused = SDL_GetKeyboardFocus() == g_window;
    SDL_GameController* controller = g_controller;
    if (controller && !SDL_GameControllerGetAttached(controller)) controller = NULL;
    for (int action = 0; action <= GB_INPUT_ACTION_START; ++action) {
        for (int slot = 0; slot < 2; ++slot) {
            const GBInputBinding& key = g_keyboard_bindings[action][slot];
            g_keyboard_binding_pressed[action][slot] = focused &&
                key.kind == GB_INPUT_BINDING_KEY && key.code >= 0 &&
                key.code < SDL_NUM_SCANCODES && keys[key.code];
            const GBInputBinding& pad = g_controller_bindings[action][slot];
            g_controller_button_binding_pressed[action][slot] = controller &&
                pad.kind == GB_INPUT_BINDING_CONTROLLER_BUTTON &&
                SDL_GameControllerGetButton(controller, (SDL_GameControllerButton)pad.code);
            const bool axis = pad.kind == GB_INPUT_BINDING_CONTROLLER_AXIS_POSITIVE ||
                              pad.kind == GB_INPUT_BINDING_CONTROLLER_AXIS_NEGATIVE;
            g_controller_axis_binding_pressed[action][slot] = controller && axis &&
                binding_active_for_axis_value(pad,
                    SDL_GameControllerGetAxis(controller, (SDL_GameControllerAxis)pad.code));
        }
    }
    g_rr_input_sample_time = now;
    update_effective_joypad_state();
    if (ctx && input_transition_creates_press(previous_dpad, previous_buttons,
            g_joypad_dpad, g_joypad_buttons, !(ctx->io[0] & 0x10), !(ctx->io[0] & 0x20)))
        request_joypad_interrupt(ctx);
    record_manual_input_state(ctx ? ctx->total_cycles : 0);
}

static void rr_gb_refresh_joyp(GBContext* ctx) {
    rr_gb_sample_input(ctx, false);
}
