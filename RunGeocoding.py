#=================================================
#
# Project: Interactive Terminal Geocoder
# Updated: 2026-09-08
# Author: Wei Liu
#
#=================================================


import os
import string
import multiprocessing as mp
import tqdm
import pandas as pd
from arcgis.gis import GIS
from arcgis.geocoding import geocode
import warnings

# Ignore all warnings
warnings.filterwarnings("ignore")

# Initialize GIS connection globally
gis = GIS()

# Ensure selected column is address-like
def not_address_like(series, address_pattern):
    """Check if the column values are address-like based on a regex pattern."""
    address_like = series.astype("string").str.contains(address_pattern, na=False)
    return address_like.sum() / len(series) < 0.5

# Geocode function
def arcgis_geocode(single_address):
    """Geocode a single address using ArcGIS."""
    if not isinstance(single_address, str) or len(single_address.strip()) < 10:
        return ('', '', '')
    try:
        geocoded_result = geocode(address=single_address, location_type="rooftop", out_sr=4326)
        if len(geocoded_result) > 0:
            lon = geocoded_result[0]['location']['x']
            lat = geocoded_result[0]['location']['y']
            score = geocoded_result[0]['score']
        else:
            lon, lat, score = '', '', ''
        return (lon, lat, score)
    except Exception as e:
        return ('', '', '')  # Return empty result on error
    
def select_address_column(input_df, column_dict):
    # -----------------------------------------
    # Address pattern
    # -----------------------------------------

    address_pattern = (
        r'\d{1,6}'
        r'(\s+[A-Za-z0-9#]+(?:[\s\-\.]?[A-Za-z0-9]+)*)'
        r'(\s+'
        r'(Street|St|Ave|Avenue|Rd|Road|'
        r'Blvd|Boulevard|Drive|Dr|Court|Ct|Lane|Ln|'
        r'Terrace|Ter|Plaza|Pkwy|Parkway|Circle|Cir|'
        r'Square|Sq|Loop|Crescent|Cres|Way|Trail|Trl|'
        r'Unit|Suite|Apt|Apartment|Floor))?'
        r'(\s+\d{0,5}[A-Za-z]?)?'
    )

    # -----------------------------------------
    # Ask user to select address column
    # -----------------------------------------

    while True:

        try:
            addr_col_idx = int(
                input("\nIndex of the full address column: ")
            )

        except ValueError:
            print("\nInvalid input. Please enter a number.")
            continue

        # -----------------------------------------
        # Check column index
        # -----------------------------------------

        if addr_col_idx not in column_dict:
            print(
                "\nOut of index range. "
                "Please enter a valid index."
            )
            continue

        addr_col = column_dict[addr_col_idx]

        # -----------------------------------------
        # Validate address column
        # -----------------------------------------

        if not_address_like(
            input_df[addr_col],
            address_pattern
        ):
            print(
                f"\nColumn '{addr_col}' does NOT "
                "look like an address column."
            )
            print("Please select another column.")
            continue

        # -----------------------------------------
        # Valid address column
        # -----------------------------------------

        print(
            f"\nAddress column selected: '{addr_col}'"
        )

        return addr_col

def main():
    # Set working directory
    wd = input("Set working directory: ").strip(string.punctuation)
    os.chdir(wd)
    
    status = True
    while status:
        files = os.listdir()
        valid_files = [file for file in files if file.endswith(('.xlsx', '.xls', '.csv'))]
        # Create dictionary with column indices starting from 1
        valid_files_dict = {index + 1: value for index, value in enumerate(valid_files)}

        # Print out all valid files in the working folder
        print("\nAll valid files:")
        for key, value in valid_files_dict.items():
            print(f"{key}: {value}")

        # Ask for a file to be geocoded and validate input
        confirm_selected_file = False
        while not confirm_selected_file:
            try:
                file_idx = int(input("\nIndex of the file: "))
                if file_idx in valid_files_dict:
                    selected_file = valid_files_dict[file_idx]
                    while True:
                        confirm_y_n = input(
                            f"\nPerform geocoding to file named \"{selected_file}\" (y/n): "
                        ).lower()
                        if confirm_y_n == 'y':
                            confirm_selected_file = True
                            break
                        elif confirm_y_n == 'n':
                            print('\nSelect another file')
                            break
                        else:
                            print("\nPlease input \"y\" or \"n\"")
                else:
                    print("\nOut of index range. Please enter a valid index.")
            except ValueError:
                print("\nInvalid input. Please enter a number.")

        # Process data frame
        if selected_file.endswith(".csv"):
            with open(selected_file, "r", encoding="utf-8") as file:
                for i in range(2):
                    line = file.readline().strip()
                    print(f"Line {i + 1}:\n", line)
            input_sep = input('\nColumn separator is comma(,) semicolon(;) tab(\\t) or pipe(|):').strip()
            input_df = pd.read_csv(selected_file, sep=input_sep)
            print("\nReview formatted data table:\n")
            print(input_df.head(2))
        else:
            input_df = pd.read_excel(selected_file)
        input_df = input_df.dropna(how="all").reset_index(drop=True)
        column_list = list(input_df.columns)

        # Create dictionary with column indices starting from 1
        column_dict = {index + 1: value for index, value in enumerate(column_list)}

        # Print column options
        print("\n\nAll columns in this file:")
        for key, value in column_dict.items():
            print(f"{key}: {value}")

        addr_col = select_address_column(input_df, column_dict)

        # Geocode addresses using multiprocessing through ArcGIS Geocoding API
        print("\n")
        addr_list = input_df[addr_col].tolist()
        cpu_count = max(mp.cpu_count() - 1, 1)
        with mp.Pool(cpu_count) as pool:
            results = list(
                tqdm.tqdm(
                    pool.imap(arcgis_geocode, addr_list),
                    total = len(addr_list),
                    desc = "Geocoding in progress"
                )
            )

        # Results check
        print(f"\nNumber of addresses processed: {len(addr_list)}")

        # Append results back to the original DataFrame
        results_df = pd.DataFrame(results, columns=['Longitude', 'Latitude', 'Score'])
        output_df = pd.concat([input_df, results_df], axis=1)

        # Save as CSV in the same directory
        base_name = os.path.basename(selected_file)
        file_name_without_extension, _ = os.path.splitext(base_name)
        try:
            output_df.to_csv(file_name_without_extension + "_geocoded.csv", index=False)
            print(f"\nGeocoded data saved as {file_name_without_extension}_geocoded.csv")
        except Exception as e:
            print("\nError saving output CSV.")

        while True:
            next_y_n = input(f"\nGeocode next file (y/n): ").lower()
            if next_y_n == 'n':
                input("\nPress Enter to exit...")
                status = False
                break
            elif next_y_n == 'y':
                break
            else:
                print("\nPlease input \"y\" or \"n\"")

if __name__ == "__main__":
    main()
