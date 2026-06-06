def test_ui_modules_import_without_starting_tk():
    import app.ui.allocation_page
    import app.ui.dashboard
    import app.ui.main_window
    import app.ui.pac_executions_page
    import app.ui.pac_simulation_page
    import app.ui.performance_page
    import app.ui.rebalance_page
    import app.ui.settings_page

    assert app.ui.main_window.MainWindow is not None
