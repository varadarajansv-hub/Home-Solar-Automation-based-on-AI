pythonimport numpy as np

np.random.seed(8) # Seed for repeatable local weather profiles

class HomeSolarOptimization:
    def __init__(self, billing_cycles=1):
        # 1 Billing Cycle = 60 Days (Bi-monthly billing)
        self.days = billing_cycles * 60
        self.hours = 24
        self.total_steps = self.days * self.hours
        
        # System Configuration
        self.solar_capacity_kwp = 3.0       
        self.battery_capacity_kwh = 5.0     
        self.battery_efficiency = 0.88      
        
        # Minimum SoC Buffer Configuration (15% reserve for morning peaks)
        self.min_soc_percentage = 0.15      
        self.min_battery_soc = self.battery_capacity_kwh * self.min_soc_percentage

    def get_DISCOM_base_rate(self, total_units_bimonthly):
        """Returns progressive domestic tier structure (Bi-monthly units breakdown)."""
        if total_units_bimonthly <= 100:
            return 0.00
        elif total_units_bimonthly <= 400:
            return 4.60
        elif total_units_bimonthly <= 500:
            return 6.15
        elif total_units_bimonthly <= 600:
            return 8.55
        elif total_units_bimonthly <= 800:
            return 9.65
        else:
            return 11.80

    def calculate_tod_multiplier(self, hour):
        """Applies Time-of-Day (ToD) weighting factors."""
        if 9 <= hour < 17:
            return 0.80   # Solar Window: 20% Discount
        elif (6 <= hour < 10) or (18 <= hour < 22):
            return 1.15   # Peak Windows: 15% Surcharge
        else:
            return 1.00   # Standard off-peak hours

    def run_simulation(self, use_pv=True, use_battery=True, use_thermal=True):
        """Generalized simulation loop to support scenario comparison."""
        battery_soc = 2.0  # Initial SoC
        
        # Base Indian household load curve
        base_load = np.array([0.5, 0.4, 0.4, 0.3, 0.3, 0.5, 0.8, 1.0, 0.7, 0.6, 0.5, 0.5, 
                              0.6, 0.6, 0.5, 0.5, 0.7, 1.1, 2.2, 2.6, 2.3, 1.6, 1.0, 0.6])
        load_profile = np.tile(base_load, self.days)
        
        # Thermal Solar Integration (Separated for explicit metric tracking)
        water_heater_shave = np.array([0,0,0,0,0,0,0.4,0.5,0.3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0])
        solar_cooker_shave   = np.array([0,0,0,0,0,0,0,0,0,0,0,0.5,0.6,0.6,0,0,0,0,0,0,0,0,0,0])
        thermal_shave = water_heater_shave + solar_cooker_shave
        
        total_water_heater_kwh = np.sum(water_heater_shave) * self.days if use_thermal else 0.0
        total_solar_cooker_kwh = np.sum(solar_cooker_shave) * self.days if use_thermal else 0.0
        
        if use_thermal:
            load_profile -= np.tile(thermal_shave, self.days)
        load_profile = np.clip(load_profile, 0.1, None)
        
        # PV Generation profile
        if use_pv:
            base_solar = np.array([0,0,0,0,0,0,0,0.15,0.5,1.2,2.1,2.8,3.0,2.9,2.2,1.3,0.4,0.05,0,0,0,0,0,0])
            solar_profile = np.tile(base_solar, self.days)
            for d in range(self.days):
                weather_anomaly = np.random.choice([1.0, 0.8, 0.4, 0.15], p=[0.6, 0.2, 0.15, 0.05])
                idx = d * 24
                solar_profile[idx:idx+24] *= weather_anomaly
        else:
            solar_profile = np.zeros(self.total_steps)
            
        cumulative_imported_units = 0.0
        cumulative_exported_units = 0.0
        total_billing_cost = 0.0
        
        for step in range(self.total_steps):
            hour = step % 24
            current_load = load_profile[step]
            current_solar = solar_profile[step]
            
            base_rate = self.get_DISCOM_base_rate(cumulative_imported_units)
            tod_multiplier = self.calculate_tod_multiplier(hour)
            current_tariff = base_rate * tod_multiplier
            
            net_energy = current_solar - current_load
            
            if net_energy > 0:
                if use_battery:
                    room_in_battery = self.battery_capacity_kwh - battery_soc
                    charge_power = min(net_energy, room_in_battery)
                    battery_soc += charge_power * self.battery_efficiency
                    excess_to_grid = net_energy - charge_power
                else:
                    excess_to_grid = net_energy
                    
                cumulative_exported_units += excess_to_grid
                total_billing_cost -= excess_to_grid * 3.10
            else:
                required_deficit = abs(net_energy)
                
                if use_battery and tod_multiplier >= 1.0 and battery_soc > self.min_battery_soc:
                    available_discharge = battery_soc - self.min_battery_soc
                    discharge_power = min(required_deficit, available_discharge)
                    battery_soc -= discharge_power
                    grid_draw = required_deficit - (discharge_power * self.battery_efficiency)
                else:
                    grid_draw = required_deficit
                    
                cumulative_imported_units += grid_draw
                total_billing_cost += grid_draw * current_tariff
                
        return {
            "bill": max(0, total_billing_cost),
            "imports": cumulative_imported_units,
            "exports": cumulative_exported_units,
            "water_thermal_kwh": total_water_heater_kwh,
            "cooker_thermal_kwh": total_solar_cooker_kwh,
            "final_soc": battery_soc
        }

    def generate_comprehensive_metrics(self):
        # 1. Baseline Scenario (Standard House: No Solar PV, No Battery, No Thermal)
        baseline = self.run_simulation(use_pv=False, use_battery=False, use_thermal=False)
        
        # 2. Fully Optimized Scenario (With Solar PV, Battery Management, Thermal Solar)
        optimized = self.run_simulation(use_pv=True, use_battery=True, use_thermal=True)
        
        # 3. Intermediate Scenario (To isolate Thermal Solar impact precisely)
        thermal_only = self.run_simulation(use_pv=False, use_battery=False, use_thermal=True)
        
        # Savings Extractions
        total_combined_savings = baseline["bill"] - optimized["bill"]
        thermal_isolated_savings = baseline["bill"] - thermal_only["bill"]
        pv_battery_isolated_savings = total_combined_savings - thermal_isolated_savings

        return {
            "Total Evaluation Period (Days)": self.days,
            "Baseline DISCOM Bill (No Solar - INR)": round(baseline["bill"], 2),
            "Optimized DISCOM Bill (With Solar - INR)": round(optimized["bill"], 2),
            "---------------------------------------": "-------------------",
            "Thermal Energy Saved: Water Heating (kWh)": round(optimized["water_thermal_kwh"], 1),
            "Thermal Energy Saved: Solar Cooking (kWh)": round(optimized["cooker_thermal_kwh"], 1),
            "Total Units Imported from DISCOM (kWh)": round(optimized["imports"], 1),
            "Total Units Exported to DISCOM (kWh)": round(optimized["exports"], 1),
            "End-of-Cycle Battery Reserve (kWh)": round(optimized["final_soc"], 2),
            "--------------------------------------- ':": "-------------------",
            "Savings via Thermal Solar Shaving (INR)": round(thermal_isolated_savings, 2),
            "Savings via PV + Battery Heuristics (INR)": round(pv_battery_isolated_savings, 2),
            "TOTAL FINANCIAL SAVINGS FOR OWNER (INR)": round(total_combined_savings, 2)
        }

# Execute metrics breakdown
optimizer = HomeSolarOptimization(billing_cycles=1)
metrics = optimizer.generate_comprehensive_metrics()
for key, value in metrics.items():
    print(f"{key}: {value}")
