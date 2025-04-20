(function(section) {
    // Create an object to store all ticket information
    const ticketInfo = {
      seatingData: {},
      priceData: {},
      availableSeats: [],
      seatDetails: [],
      seatSummary: {},
      availabilityMap: []
    };
    
    // Collect seating data arrays
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
  
    // Generate detailed seat map with status
    if (typeof rowNames !== 'undefined' && typeof rowSeatStatus !== 'undefined') {
      // Create a visual map of seat availability using the system's indicators
      ticketInfo.availabilityMap = rowNames.map((rowName, rowIndex) => {
        const rowStatuses = rowSeatStatus[rowIndex].map(status => status).join('');
        return `Row ${rowName}: ${rowStatuses}`;
      });
      
      // Create detailed information for all seats
      for (let rowIndex = 0; rowIndex < rowNames.length; rowIndex++) {
        const rowName = rowNames[rowIndex];
        
        for (let seatIndex = 0; seatIndex < rowSeatStatus[rowIndex].length; seatIndex++) {
          const seatStatus = rowSeatStatus[rowIndex][seatIndex];
          const seatCurrentStatus = rowSeatCurrentStatus ? rowSeatCurrentStatus[rowIndex][seatIndex] : null;
          const seatRealStatus = rowSeatRealStatus ? rowSeatRealStatus[rowIndex][seatIndex] : null;
          const seatName = rowSeatName ? rowSeatName[rowIndex][seatIndex] : `Seat ${seatIndex + 1}`;
          const seatNote = rowSeatNote ? rowSeatNote[rowIndex][seatIndex] : null;
          const holdComment = rowSeatHoldComment ? rowSeatHoldComment[rowIndex][seatIndex] : null;
          const priceLevelId = rowPriceLevelID ? rowPriceLevelID[rowIndex][seatIndex] : null;
          
          // Get price information
          let priceInfo = null;
          let priceCodeInfo = null;
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
          
          // Use 'O' as the indicator for available seats
          const isAvailable = seatStatus === 'O';
          
          // Add to all seats list
          const seatDetail = {
            rowIndex,
            seatIndex,
            row: rowName,
            seat: seatName,
            seatIdentifier: `${rowName}-${seatName}`,
            status: seatStatus,
            currentStatus: seatCurrentStatus,
            realStatus: seatRealStatus,
            isAvailable: isAvailable,
            note: seatNote,
            holdComment: holdComment,
            priceLevelId: priceLevelId,
            price: priceInfo ? priceInfo.ticketPriceStr : null,
            priceNum: priceInfo ? priceInfo.ticketPriceNum : null,
            priceCode: priceCodeInfo
          };
          
          ticketInfo.seatDetails.push(seatDetail);
          
          // Only include if seat is available (status is 'O') in the available seats list
          if (isAvailable) {
            ticketInfo.availableSeats.push(seatDetail);
          }
          
          // Count seats by status for summary
          if (!ticketInfo.seatSummary[seatStatus]) {
            ticketInfo.seatSummary[seatStatus] = 0;
          }
          ticketInfo.seatSummary[seatStatus]++;
        }
      }
    }
    
    // Calculate availability percentage
    const totalSeats = ticketInfo.seatDetails.length;
    const availableCount = ticketInfo.availableSeats.length;
    ticketInfo.availabilityPercentage = totalSeats > 0 ? 
      ((availableCount / totalSeats) * 100).toFixed(2) + '%' : '0%';
  
    // Group available seats by row for easier viewing
    ticketInfo.availableByRow = {};
    ticketInfo.availableSeats.forEach(seat => {
      if (!ticketInfo.availableByRow[seat.row]) {
        ticketInfo.availableByRow[seat.row] = [];
      }
      ticketInfo.availableByRow[seat.row].push(seat);
    });
    
    // Group available seats by price
    ticketInfo.availableByPrice = {};
    ticketInfo.availableSeats.forEach(seat => {
      const price = seat.price || 'Unknown';
      if (!ticketInfo.availableByPrice[price]) {
        ticketInfo.availableByPrice[price] = [];
      }
      ticketInfo.availableByPrice[price].push(seat);
    });
    
    // Calculate summary statistics
    ticketInfo.summary = {
        totalRows: ticketInfo.seatingData.rowNames ? ticketInfo.seatingData.rowNames.length : 0,
        totalSeats: totalSeats,
        availableSeats: availableCount,
        availabilityPercentage: ticketInfo.availabilityPercentage,
        statusBreakdown: ticketInfo.seatSummary
    };

    // Create a more descriptive status breakdown
    ticketInfo.statusDescription = {
        'O': 'Available',
        'X': 'Unavailable/Sold'
    };

    console.log('Complete Ticket Information:', ticketInfo);
    console.log('Available Seat Count:', availableCount);
    console.log('Availability Percentage:', ticketInfo.availabilityPercentage);
    console.log('Status Breakdown:', ticketInfo.seatSummary);
    console.log('Status Legend:', ticketInfo.statusDescription);
    console.log('Available Seats by Row:', ticketInfo.availableByRow);
    console.log('Available Seats by Price:', ticketInfo.availableByPrice);
    console.log('Seat Status Map:');
    ticketInfo.availabilityMap.forEach(row => console.log(row));

    return {
        all: ticketInfo,
        available: ticketInfo.availableSeats,
        availableByRow: ticketInfo.availableByRow,
        availableByPrice: ticketInfo.availableByPrice,
        summary: ticketInfo.summary,
        map: ticketInfo.availabilityMap,
        statusLegend: ticketInfo.statusDescription,
        section: section
    };
})(section);