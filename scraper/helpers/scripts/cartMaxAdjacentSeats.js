/**
 * Etix Adjacent Seat Selector
 * This script finds the largest group of adjacent seats and adds them to the cart
 * It automatically selects the maximum allowed by the ticket limit, starting from the end of the row
 */
(function() {
  // First, check if we're already on the manifest page
  if (document.body.id !== "add-seat-show-manifest" && 
      document.body.id !== "add-seat-manifest") {
    console.error("Not on the manifest page - navigate there first");
    return;
  }
  
  // Get the maximum ticket limit - try to get from window context first
  const determineMaxTicketLimit = () => {
    console.log("Determining maximum ticket limit from system...");
    
    // Log all potentially relevant ticket limit variables for debugging
    console.log("upperTicketLimitPerOrder:", typeof upperTicketLimitPerOrder !== 'undefined' ? upperTicketLimitPerOrder : "undefined");
    console.log("ticketUpperLimits:", typeof ticketUpperLimits !== 'undefined' ? JSON.stringify(ticketUpperLimits) : "undefined");
    console.log("ticketLowerLimits:", typeof ticketLowerLimits !== 'undefined' ? JSON.stringify(ticketLowerLimits) : "undefined");
    console.log("multipleLimitPerPriceCode:", typeof multipleLimitPerPriceCode !== 'undefined' ? JSON.stringify(multipleLimitPerPriceCode) : "undefined");
    
    let ticketLimit = null;
    let source = "default";
    
    // First, check the upperTicketLimitPerOrder which is the most reliable source
    if (typeof upperTicketLimitPerOrder === 'number' && upperTicketLimitPerOrder > 0) {
      ticketLimit = upperTicketLimitPerOrder;
      source = "upperTicketLimitPerOrder";
    }
    // Second, check ticket upper limits array if available
    else if (Array.isArray(ticketUpperLimits) && ticketUpperLimits.length > 0) {
      // Find the minimum value in the array as the effective limit
      const filteredLimits = ticketUpperLimits.filter(limit => typeof limit === 'number' && limit > 0);
      if (filteredLimits.length > 0) {
        ticketLimit = Math.min(...filteredLimits);
        source = "ticketUpperLimits";
      }
    }
    
    // As a fallback, check if the limit is visible on the DOM
    if (!ticketLimit) {
      try {
        // Look for limit text in the page content
        const pageContent = document.body.innerText;
        const limitMatch = pageContent.match(/Limit (\d+) per order/i);
        if (limitMatch && limitMatch[1]) {
          ticketLimit = parseInt(limitMatch[1], 10);
          source = "page content";
        }
      } catch (err) {
        console.warn("Error searching page content for ticket limit:", err);
      }
    }
    
    // If we still don't have a limit, search page scripts
    if (!ticketLimit) {
      try {
        // Get all scripts on the page
        const scripts = document.querySelectorAll('script:not([src])');
        for (const script of scripts) {
          const content = script.textContent;
          if (content.includes('upperTicketLimitPerOrder')) {
            const match = content.match(/upperTicketLimitPerOrder\s*=\s*(\d+)/);
            if (match && match[1]) {
              ticketLimit = parseInt(match[1], 10);
              source = "script content";
              break;
            }
          }
        }
      } catch (err) {
        console.warn("Error searching scripts for ticket limit:", err);
      }
    }
    
    // Last resort: use hard-coded default of 8 (common Etix limit)
    if (!ticketLimit || ticketLimit <= 0) {
      ticketLimit = 8;
      source = "default value";
    }
    
    console.log(`Using ticket limit of ${ticketLimit} (source: ${source})`);
    return ticketLimit;
  };
  
  // Make sure we have access to the ticket data
  if (!window.ticketData) {
    console.error("No ticketData found in window context - run the data collection script first");
    // Generate data if not available
    window.ticketData = generateTicketData();
    if (!window.ticketData || !window.ticketData.adjacentSeats || window.ticketData.adjacentSeats.length === 0) {
      console.error("Failed to generate ticket data");
      return;
    }
  }
  
  // Generate ticket data function (fallback if window.ticketData doesn't exist)
  function generateTicketData() {
    console.log("Generating ticket data from window variables...");
    
    // Create data structure with the same format as our original script
    const ticketInfo = {
      seatingData: {},
      priceData: {},
      availableSeats: [],
      seatDetails: [],
      seatSummary: {},
      availabilityMap: [],
      adjacentSeatGroups: []
    };
    
    // Collect seating data arrays from window context
    if (typeof rowNames !== 'undefined') ticketInfo.seatingData.rowNames = rowNames;
    if (typeof rowPriceLevelID !== 'undefined') ticketInfo.seatingData.rowPriceLevelID = rowPriceLevelID;
    if (typeof rowSeatCurrentStatus !== 'undefined') ticketInfo.seatingData.rowSeatCurrentStatus = rowSeatCurrentStatus;
    if (typeof rowSeatHoldComment !== 'undefined') ticketInfo.seatingData.rowSeatHoldComment = rowSeatHoldComment;
    if (typeof rowSeatName !== 'undefined') ticketInfo.seatingData.rowSeatName = rowSeatName;
    if (typeof rowSeatNote !== 'undefined') ticketInfo.seatingData.rowSeatNote = rowSeatNote;
    if (typeof rowSeatRealStatus !== 'undefined') ticketInfo.seatingData.rowSeatRealStatus = rowSeatRealStatus;
    if (typeof rowSeatStatus !== 'undefined') ticketInfo.seatingData.rowSeatStatus = rowSeatStatus;
    if (typeof rowlessSection !== 'undefined') ticketInfo.seatingData.rowlessSection = rowlessSection;
    
    // Collect price information
    if (typeof priceInfos !== 'undefined') ticketInfo.priceData.priceInfos = priceInfos;
    if (typeof priceCodeIdDescMap !== 'undefined') ticketInfo.priceData.priceCodeIdDescMap = priceCodeIdDescMap;
    if (typeof priceCodeIdNameMap !== 'undefined') ticketInfo.priceData.priceCodeIdNameMap = priceCodeIdNameMap;
    if (typeof priceCodeIds !== 'undefined') ticketInfo.priceData.priceCodeIds = priceCodeIds;
    if (typeof priceCodeName !== 'undefined') ticketInfo.priceData.priceCodeName = priceCodeName;
    if (typeof priceCodePriceLevels !== 'undefined') ticketInfo.priceData.priceCodePriceLevels = priceCodePriceLevels;
    
    // Find adjacent available seats
    if (typeof rowNames !== 'undefined' && typeof rowSeatStatus !== 'undefined') {
      for (let rowIndex = 0; rowIndex < rowNames.length; rowIndex++) {
        const rowName = rowNames[rowIndex];
        let currentGroup = [];
        
        for (let seatIndex = 0; seatIndex < rowSeatStatus[rowIndex].length; seatIndex++) {
          const seatStatus = rowSeatStatus[rowIndex][seatIndex];
          const seatName = rowSeatName ? rowSeatName[rowIndex][seatIndex] : `Seat ${seatIndex + 1}`;
          
          // If seat is available, add to current group
          if (seatStatus === 'O') {
            const priceLevelId = rowPriceLevelID ? rowPriceLevelID[rowIndex][seatIndex] : null;
            let priceInfo = null;
            let priceCodeInfo = null;
            
            // Find price info for this seat
            if (priceLevelId && typeof priceInfos !== 'undefined' && priceCodeIds) {
              for (const priceCodeId of priceCodeIds) {
                const keyId = `${priceCodeId}&${priceLevelId}`;
                const foundPriceInfo = priceInfos.find(p => p.keyId === keyId);
                if (foundPriceInfo) {
                  priceInfo = foundPriceInfo;
                  priceCodeInfo = {
                    id: priceCodeId,
                    name: priceCodeIdNameMap ? priceCodeIdNameMap[priceCodeId] : null,
                    description: priceCodeIdDescMap ? priceCodeIdDescMap[priceCodeId] : null
                  };
                  break;
                }
              }
            }
            
            const seatDetail = {
              rowIndex,
              seatIndex,
              row: rowName,
              seat: seatName,
              seatIdentifier: `${rowName}-${seatName}`,
              status: seatStatus,
              isAvailable: true,
              priceLevelId: priceLevelId,
              price: priceInfo ? priceInfo.ticketPriceStr : null,
              priceNum: priceInfo ? priceInfo.ticketPriceNum : null,
              priceCode: priceCodeInfo
            };
            
            currentGroup.push(seatDetail);
          } else {
            // If we have adjacent seats in the current group, save and start a new group
            if (currentGroup.length > 1) {
              ticketInfo.adjacentSeatGroups.push({
                row: rowName,
                seats: [...currentGroup],
                count: currentGroup.length,
                priceRange: calculatePriceRange(currentGroup)
              });
            }
            currentGroup = [];
          }
        }
        
        // Check for adjacent seats at the end of the row
        if (currentGroup.length > 1) {
          ticketInfo.adjacentSeatGroups.push({
            row: rowName,
            seats: [...currentGroup],
            count: currentGroup.length,
            priceRange: calculatePriceRange(currentGroup)
          });
        }
      }
    }
    
    // Helper function to calculate price range
    function calculatePriceRange(seats) {
      const prices = seats
        .map(seat => parseFloat(seat.priceNum))
        .filter(price => !isNaN(price));
      
      if (prices.length === 0) return { min: null, max: null, total: null };
      
      const min = Math.min(...prices);
      const max = Math.max(...prices);
      const total = prices.reduce((sum, price) => sum + price, 0);
      
      return { 
        min: min.toFixed(2), 
        max: max.toFixed(2), 
        total: total.toFixed(2),
        average: (total / prices.length).toFixed(2)
      };
    }
    
    // Sort by largest group first
    ticketInfo.adjacentSeatGroups.sort((a, b) => b.count - a.count);
    
    return {
      adjacentSeats: ticketInfo.adjacentSeatGroups
    };
  }
  
  // Get the adjacent seat groups
  const adjacentGroups = window.ticketData.adjacentSeats || [];
  
  if (adjacentGroups.length === 0) {
    console.error("No adjacent seat groups found");
    return;
  }
  
  // Get the first (largest) group
  const bestGroup = adjacentGroups[0];
  console.log(`Found ${adjacentGroups.length} adjacent seat groups`);
  console.log(`Best group: ${bestGroup.count} seats in row ${bestGroup.row}`);
  
  // Clear any existing seat selections - FIX: Added validation for seat IDs
  const currentSelectedSeats = document.querySelectorAll('circle.selectedTd');
  console.log(`Found ${currentSelectedSeats.length} existing seat selections to clear`);
  
  // Alternative approach: use the built-in mechanism to clear selections
  try {
    // Try a safer approach first - use dynamicList() to get the current selections
    if (typeof selectedImageIDByManifest !== 'undefined' && Array.isArray(selectedImageIDByManifest)) {
      // Make a copy since we're modifying the array while iterating
      const selectedSeats = [...selectedImageIDByManifest].filter(id => id && id.trim() !== '');
      console.log(`Clearing ${selectedSeats.length} seats using selectedImageIDByManifest`);
      
      for (const seatId of selectedSeats) {
        if (seatId && document.getElementById(seatId)) {
          try {
            removeSeat(seatId);
          } catch (err) {
            console.warn(`Error removing seat ${seatId}:`, err);
          }
        }
      }
    } else {
      // Fallback to manual approach if array isn't available
      currentSelectedSeats.forEach(seat => {
        const seatId = seat.id;
        if (seatId && seatId.trim() !== '') {
          try {
            console.log(`Removing seat: ${seatId}`);
            removeSeat(seatId);
          } catch (err) {
            console.warn(`Error removing seat ${seatId}:`, err);
            // Try manual deselection as fallback
            try {
              if (typeof setClassName === 'function' && typeof unSelectSeat === 'function') {
                const originalClass = getSeatBackgroundClassName(seat.getAttribute('rowIndex'), seat.getAttribute('seatIndex'));
                setClassName(seat, originalClass);
                unSelectSeat(seat);
              }
            } catch (innerErr) {
              console.warn("Fallback deselection failed:", innerErr);
            }
          }
        } else {
          console.warn("Found seat with invalid ID, skipping removal");
        }
      });
    }
  } catch (err) {
    console.error("Error clearing seat selections:", err);
    console.log("Continuing with selection process...");
  }
  
  // Determine the maximum number of tickets we can purchase
  const maxTicketLimit = determineMaxTicketLimit();
  console.log(`Maximum ticket limit: ${maxTicketLimit}`);
  
  // Calculate how many seats to select - take the minimum of the max limit and available seats
  const seatCount = Math.min(maxTicketLimit, bestGroup.count);
  console.log(`Selecting ${seatCount} seats out of ${bestGroup.count} available adjacent seats`);
  
  // Take the last N seats from the group (start from the end of the row)
  // Reverse the array so we can take the last seats (highest numbers in row)
  const reversedSeats = [...bestGroup.seats].reverse();
  const seatsToSelect = reversedSeats.slice(0, seatCount);
  
  console.log(`Selecting ${seatCount} adjacent seats in row ${bestGroup.row}, starting from the end`);
  console.log(`Seats: ${seatsToSelect.map(s => s.seat).join(', ')}`);
  
  // Select each seat using window context functions
  let seatsSelected = 0;
  
  for (const seat of seatsToSelect) {
    const seatElement = document.querySelector(`circle[id="IMG${seat.rowIndex}C${seat.seatIndex}"]`);
    
    if (seatElement) {
      // Use the native window context function
      try {
        seatToggle(seatElement);
        
        // Check if the seat was successfully selected
        if (getClassName(seatElement) === "selectedTd") {
          seatsSelected++;
          
          // Set price code if available
          if (seat.priceCode && seat.priceCode.id) {
            setAttribute(seatElement, "P", seat.priceCode.id);
          }
        }
      } catch (err) {
        console.error(`Error selecting seat ${seat.seatIdentifier}:`, err);
      }
    } else {
      console.warn(`Seat ${seat.seatIdentifier} not found in the DOM`);
    }
  }
  
  console.log(`Selected ${seatsSelected} seats out of ${seatCount} attempted`);
  
  // If we selected any seats, automatically add them to cart
  if (seatsSelected > 0) {
    try {
      console.log(`Automatically adding ${seatsSelected} seats to cart...`);
      doBuyTicket();
    } catch (err) {
      console.error("Error adding seats to cart:", err);
    }
  } else {
    console.log("No seats were successfully selected");
  }
})(); 