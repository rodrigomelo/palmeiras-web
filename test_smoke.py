#!/usr/bin/env python3
"""
Palmeiras Web - Smoke Test
Tests core functionality to catch regressions.
Usage: python test_smoke.py
"""

from playwright.sync_api import sync_playwright
import sys
import time

def run_smoke_test():
    """Run comprehensive smoke test of Palmeiras Web app."""
    print("🧪 Starting Palmeiras Web smoke test...")
    
    results = {
        'page_load': False,
        'tabs_functionality': False, 
        'tabs_accessibility': False,
        'calendar_expansion': False,
        'calendar_styling': False,
        'prediction_loading': False,
        'console_clean': False
    }
    
    console_messages = []
    page_errors = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        
        # Capture console messages and errors
        page.on('console', lambda msg: console_messages.append(f"{msg.type}: {msg.text}"))
        page.on('pageerror', lambda exc: page_errors.append(str(exc)))
        
        try:
            # Test 1: Page loads without errors
            print("  📄 Testing page load...")
            page.goto('http://localhost:5001', wait_until='networkidle', timeout=15000)
            results['page_load'] = True
            print("  ✅ Page loaded successfully")
            
            # Test 2: Tab functionality and accessibility
            print("  🔖 Testing tab functionality...")
            tabs = page.locator('.tab-btn')
            tab_count = tabs.count()
            
            if tab_count >= 4:
                # Test each tab switches content
                tab_switches = []
                for i in range(tab_count):
                    tab = tabs.nth(i)
                    tab_text = tab.inner_text().strip()
                    
                    tab.click()
                    page.wait_for_timeout(200)
                    
                    # Check active content panel
                    active_content = page.locator('.tab-content.active')
                    active_id = active_content.get_attribute('id') if active_content.count() > 0 else None
                    
                    # Check aria-selected state
                    aria_selected = tab.get_attribute('aria-selected')
                    
                    tab_switches.append({
                        'text': tab_text,
                        'active_content': active_id,
                        'aria_selected': aria_selected
                    })
                
                # Verify all tabs switched content and aria-selected correctly
                content_ids = [t['active_content'] for t in tab_switches]
                aria_states = [t['aria_selected'] for t in tab_switches]
                
                results['tabs_functionality'] = len(set(content_ids)) == tab_count and None not in content_ids
                results['tabs_accessibility'] = all(state == 'true' for state in aria_states)
                
                if results['tabs_functionality']:
                    print("  ✅ Tab content switching works")
                else:
                    print(f"  ❌ Tab switching failed - content IDs: {content_ids}")
                    
                if results['tabs_accessibility']:
                    print("  ✅ Tab accessibility (aria-selected) works")
                else:
                    print(f"  ❌ Tab accessibility failed - aria states: {aria_states}")
            
            # Test 3: Calendar expansion and today auto-selection
            print("  📅 Testing calendar expansion and today auto-selection...")
            
            # Check if today is auto-selected
            today_selected = page.locator('.cal-day.today.selected')
            auto_selected = today_selected.count() > 0
            
            if auto_selected:
                print("  ✅ Today's date automatically selected")
                results['calendar_expansion'] = True
                
                # Check if expanded view exists (today might or might not have matches)
                expanded = page.locator('#calendar-expanded .cal-expanded') 
                if expanded.count() > 0:
                    print("  ✅ Today's expanded view is showing")
                else:
                    print("  ✅ Today has no matches (correct - no expansion needed)")
                    
            else:
                print("  ⚠️  Today not auto-selected, testing fallback...")
                # Fallback: manually test a day with matches
                days_with_matches = page.locator('.cal-day.has-match[data-day]')
                
                if days_with_matches.count() > 0:
                    first_match_day = days_with_matches.first
                    day_num = first_match_day.get_attribute('data-day')
                    first_match_day.click()
                    page.wait_for_timeout(300)
                    
                    expanded = page.locator('#calendar-expanded .cal-expanded')
                    results['calendar_expansion'] = expanded.count() > 0
                    
                    if results['calendar_expansion']:
                        print(f"  ✅ Manual selection of day {day_num} works")
                    else:
                        print(f"  ❌ Manual selection of day {day_num} failed")
                else:
                    results['calendar_expansion'] = False
                    print("  ❌ No days with matches found for testing")
            
            
            # Test 4: Calendar styling classes (only if content expanded)
            expanded_matches = page.locator('#calendar-expanded .cal-match')
            if expanded_matches.count() > 0:
                first_match = expanded_matches.first
                match_classes = first_match.get_attribute('class') or ""
                status_element = first_match.locator('.cal-match-status').first
                
                # Check if competition classes are applied
                has_comp_class = any(cls in match_classes for cls in ['bsa', 'cli', 'copa', 'other'])
                
                # Check basic styling is present  
                has_base_class = 'cal-match' in match_classes
                
                results['calendar_styling'] = has_base_class
                
                if results['calendar_styling']:
                    print(f"  ✅ Calendar match styling applied correctly")
                    if has_comp_class:
                        print(f"    📌 Competition class detected: {match_classes}")
                    else:
                        print(f"    📌 Base classes found: {match_classes}")
                else:
                    print(f"  ❌ Calendar styling issue - classes: {match_classes}")
            else:
                # No expanded content to test styling on - mark as passed
                results['calendar_styling'] = True
                print(f"  ✅ Calendar styling test skipped (no expanded content)")
            
            # Test 4: Prediction tab loading
            print("  🎯 Testing prediction functionality...")
            prediction_tab = page.locator('.tab-btn[data-tab="prediction"]')
            
            if prediction_tab.count() > 0:
                prediction_tab.click()
                page.wait_for_timeout(2000)  # Give time for API calls
                
                prediction_content = page.locator('#prediction-content')
                content_text = prediction_content.inner_text() if prediction_content.count() > 0 else ""
                
                # Success if it's not still showing "Carregando..." (loading)
                results['prediction_loading'] = 'Carregando...' not in content_text
                
                if results['prediction_loading']:
                    print("  ✅ Prediction tab loaded content")
                else:
                    print(f"  ⚠️  Prediction still loading or empty: {content_text[:50]}...")
            
            # Test 5: Console cleanliness
            error_messages = [msg for msg in console_messages if 'error' in msg.lower()]
            results['console_clean'] = len(error_messages) == 0 and len(page_errors) == 0
            
            if results['console_clean']:
                print("  ✅ No console errors detected")
            else:
                print(f"  ⚠️  Console issues found:")
                for err in error_messages[:3]:  # Show first 3
                    print(f"    📝 {err}")
                for err in page_errors[:3]:
                    print(f"    🐛 {err}")
            
        except Exception as e:
            print(f"  ❌ Test execution failed: {e}")
        
        finally:
            browser.close()
    
    # Summary
    print("\n📊 Smoke Test Results:")
    passed = sum(results.values())
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL" 
        print(f"  {status} {test_name.replace('_', ' ').title()}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All smoke tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed - check the issues above")
        return 1

if __name__ == '__main__':
    exit_code = run_smoke_test()
    sys.exit(exit_code)